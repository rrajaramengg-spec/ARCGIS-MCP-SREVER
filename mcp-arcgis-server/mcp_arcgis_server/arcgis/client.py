"""
ArcGIS client for spatial data operations.

Owns a ThreadPoolExecutor to offload blocking arcgis SDK calls.
Delegates authentication to GISAuthManager.
"""

import asyncio
import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from arcgis.features import FeatureLayer, FeatureSet

from .auth import GISAuthManager
from .geometry import build_geometry_filter, featureset_to_dict

logger = logging.getLogger(__name__)

# Maximum features per query to prevent unbounded result sets
MAX_RESULT_COUNT = 2000


class BoundedLayerCache:
    """Thread-safe LRU cache for FeatureLayer instances.

    Uses OrderedDict for O(1) LRU eviction. All operations are guarded
    by a threading.Lock since FeatureLayer access happens in the thread pool.
    """

    def __init__(self, max_size: int = 100) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[str, FeatureLayer] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, url: str) -> Optional[FeatureLayer]:
        """Get a cached layer, moving it to most-recently-used position."""
        with self._lock:
            if url in self._cache:
                self._cache.move_to_end(url)
                return self._cache[url]
            return None

    def put(self, url: str, layer: FeatureLayer) -> None:
        """Add a layer to the cache, evicting LRU entry if at capacity."""
        with self._lock:
            if url in self._cache:
                self._cache.move_to_end(url)
                self._cache[url] = layer
                return
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[url] = layer

    def clear(self) -> None:
        """Remove all cached layers."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __contains__(self, url: str) -> bool:
        with self._lock:
            return url in self._cache


class ArcGISClient:
    """Client for ArcGIS operations using the official arcgis Python API.

    All blocking SDK calls are offloaded to a dedicated thread pool.
    """

    def __init__(self, auth: GISAuthManager, config=None) -> None:
        self._auth = auth
        self._config = config
        max_workers = 8
        cache_max_size = 100
        if config is not None:
            max_workers = config.thread_pool_max_workers
            cache_max_size = config.layer_cache_max_size
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="arcgis")
        self._layer_cache = BoundedLayerCache(max_size=cache_max_size)
        self._closed = False

    def close(self) -> None:
        """Shut down the thread pool executor. Called during server lifespan shutdown."""
        if not self._closed:
            self._closed = True
            self._executor.shutdown(wait=False)
            logger.info("ArcGISClient thread pool shut down")

    def _check_closed(self) -> None:
        if self._closed:
            raise RuntimeError("ArcGISClient is closed")

    def _get_feature_layer(self, layer_url: str) -> FeatureLayer:
        """Get or create a cached FeatureLayer for the given URL (blocking)."""
        cached = self._layer_cache.get(layer_url)
        if cached is not None:
            return cached

        if self._auth.is_internal_url(layer_url) and self._auth.gis is not None:
            fl = FeatureLayer(layer_url, gis=self._auth.gis)
        else:
            fl = FeatureLayer(layer_url)

        self._layer_cache.put(layer_url, fl)
        return fl

    async def _get_feature_layer_async(self, layer_url: str) -> FeatureLayer:
        """Get or create a FeatureLayer, offloading first-call instantiation to thread."""
        cached = self._layer_cache.get(layer_url)
        if cached is not None:
            return cached
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._get_feature_layer, layer_url
        )

    def _execute_query(
        self,
        layer_url: str,
        where: str,
        out_fields: str,
        return_geometry: bool,
        geometry: Optional[Dict[str, Any]],
        spatial_rel: Optional[str],
        out_sr: int,
        return_count_only: bool,
        result_offset: int,
        result_record_count: Optional[int],
    ) -> Dict[str, Any]:
        """Execute a FeatureLayer query (blocking, runs in thread pool)."""
        fl = self._get_feature_layer(layer_url)

        if return_count_only:
            query_kwargs: Dict[str, Any] = {
                "where": where,
                "return_count_only": True,
            }
            if geometry:
                query_kwargs["geometry_filter"] = build_geometry_filter(
                    geometry, spatial_rel or "esriSpatialRelIntersects"
                )
            count_result = fl.query(**query_kwargs)
            return {"count": count_result}

        # Enforce max result count
        effective_count = MAX_RESULT_COUNT
        if result_record_count is not None:
            effective_count = min(result_record_count, MAX_RESULT_COUNT)

        query_kwargs = {
            "where": where,
            "out_fields": out_fields,
            "return_geometry": return_geometry,
            "out_sr": out_sr,
            "return_all_records": False,
        }

        # Skip result_record_count for spatial queries — the arcgis SDK's
        # pagination logic calls _fetch_all_ids which crashes with
        # "objectIds=null" on many ArcGIS servers, causing a ~60s timeout
        # before the TypeError.  Without result_record_count the SDK uses
        # a single server-side query that works reliably.
        if not geometry:
            query_kwargs["result_record_count"] = effective_count

        if result_offset:
            query_kwargs["result_offset"] = result_offset

        if geometry:
            query_kwargs["geometry_filter"] = build_geometry_filter(
                geometry, spatial_rel or "esriSpatialRelIntersects"
            )

        fs: FeatureSet = fl.query(**query_kwargs)
        result = featureset_to_dict(fs)

        logger.info("Query returned %d features", result["count"])
        return result

    @staticmethod
    def _is_token_error(exc: Exception) -> bool:
        """Check if an exception is a 498/499 token error."""
        exc_str = str(exc)
        return "498" in exc_str or "499" in exc_str or "Token Required" in exc_str

    async def query_layer(
        self,
        layer_url: str,
        where: str = "1=1",
        out_fields: str = "*",
        return_geometry: bool = True,
        geometry: Optional[Dict[str, Any]] = None,
        geometry_type: Optional[str] = None,
        spatial_rel: Optional[str] = None,
        out_sr: int = 4326,
        return_count_only: bool = False,
        result_offset: int = 0,
        result_record_count: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Query features from an ArcGIS feature layer (async, non-blocking).

        Offloads the blocking fl.query() call to the thread pool.
        On 498/499 token error, refreshes GIS and retries once.
        """
        self._check_closed()

        if self._auth.is_internal_url(layer_url) and self._auth.gis is None:
            raise RuntimeError(
                f"GIS authentication failed for {layer_url}. "
                "The ArcGIS account may be locked out due to too many failed login "
                "attempts, or credentials may be incorrect. "
                "Unlock the account in the ArcGIS Portal admin console, then restart."
            )

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                self._executor,
                self._execute_query,
                layer_url, where, out_fields, return_geometry, geometry,
                spatial_rel, out_sr, return_count_only, result_offset,
                result_record_count,
            )
        except Exception as exc:
            if self._is_token_error(exc):
                logger.warning(
                    "Token error detected (%s), re-initializing GIS",
                    str(exc)[:100],
                )
                await self._auth.refresh(
                    clear_layer_cache_fn=self._layer_cache.clear
                )
                if self._auth.gis is None:
                    raise RuntimeError(
                        f"Re-initialization failed after token error for {layer_url}"
                    ) from exc
                return await loop.run_in_executor(
                    self._executor,
                    self._execute_query,
                    layer_url, where, out_fields, return_geometry, geometry,
                    spatial_rel, out_sr, return_count_only, result_offset,
                    result_record_count,
                )
            raise

    async def spatial_query(
        self,
        layer_url: str,
        geometry: Dict[str, Any],
        spatial_rel: str = "esriSpatialRelIntersects",
        where: str = "1=1",
        out_fields: str = "*",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Perform a spatial query using geometry."""
        return await self.query_layer(
            layer_url=layer_url,
            where=where,
            out_fields=out_fields,
            geometry=geometry,
            spatial_rel=spatial_rel,
            return_geometry=True,
            **kwargs,
        )

    async def get_layer_info(self, layer_url: str) -> Dict[str, Any]:
        """Get layer metadata using FeatureLayer.properties (async, non-blocking)."""
        self._check_closed()

        if self._auth.is_internal_url(layer_url) and self._auth.gis is None:
            raise RuntimeError(
                f"Authentication required for {layer_url} but GIS is not initialized."
            )

        fl = await self._get_feature_layer_async(layer_url)
        props = await asyncio.to_thread(lambda: fl.properties)

        return {
            "name": getattr(props, "name", None),
            "id": getattr(props, "id", None),
            "type": getattr(props, "type", None),
            "geometry_type": getattr(props, "geometryType", None),
            "description": getattr(props, "description", None),
            "fields": [dict(f) for f in getattr(props, "fields", [])]
            if hasattr(props, "fields")
            else [],
            "extent": dict(getattr(props, "extent", {}))
            if hasattr(props, "extent")
            else None,
            "spatial_reference": dict(getattr(props, "spatialReference", {}))
            if hasattr(props, "spatialReference")
            else None,
            "capabilities": getattr(props, "capabilities", None),
            "max_record_count": getattr(props, "maxRecordCount", None),
        }

    # ── Content search ──────────────────────────────────────────────────

    async def search_content(
        self,
        query: str,
        item_type: Optional[str] = None,
        max_items: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search ArcGIS portal content by keyword.

        Args:
            query: Search keyword(s).
            item_type: Optional item type filter (e.g. "Feature Layer").
            max_items: Maximum results to return.

        Returns:
            List of item metadata dicts.
        """
        self._check_closed()
        if self._auth.gis is None:
            raise RuntimeError(
                "search_content requires an authenticated GIS instance. "
                "Check ARCGIS_PORTAL_URL and credentials."
            )

        def _search() -> List[Dict[str, Any]]:
            gis = self._auth.gis
            results = gis.content.search(
                query=query,
                item_type=item_type,
                max_items=max_items,
            )
            return [
                {
                    "id": item.id,
                    "title": item.title,
                    "type": item.type,
                    "url": item.url,
                    "owner": item.owner,
                    "description": item.description,
                    "snippet": item.snippet,
                }
                for item in results
            ]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _search)

    # ── Field statistics ────────────────────────────────────────────────

    async def get_field_statistics(
        self,
        layer_url: str,
        field_name: str,
        statistics: Optional[List[str]] = None,
        where: str = "1=1",
    ) -> Dict[str, Any]:
        """Compute server-side statistics for a field using outStatistics.

        Args:
            layer_url: Feature layer URL.
            field_name: Field to compute statistics on.
            statistics: List of stat types (count, min, max, avg, stddev).
            where: Optional WHERE filter.

        Returns:
            Dict with computed statistics.
        """
        self._check_closed()
        if statistics is None:
            statistics = ["count", "min", "max", "avg", "stddev"]

        def _query_stats() -> Dict[str, Any]:
            fl = self._get_feature_layer(layer_url)
            out_statistics = [
                {
                    "statisticType": stat,
                    "onStatisticField": field_name,
                    "outStatisticFieldName": f"{stat}_{field_name}",
                }
                for stat in statistics
            ]
            fs = fl.query(where=where, out_statistics=out_statistics)
            if fs.features:
                return dict(fs.features[0].attributes)
            return {}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _query_stats)

    # ── Unique values ───────────────────────────────────────────────────

    async def get_unique_values(
        self,
        layer_url: str,
        field_name: str,
        where: str = "1=1",
        max_values: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get distinct values and counts for a field.

        Args:
            layer_url: Feature layer URL.
            field_name: Field to get unique values for.
            where: Optional WHERE filter.
            max_values: Maximum unique values to return.

        Returns:
            List of dicts with 'value' and 'count' keys.
        """
        self._check_closed()

        def _query_distinct() -> List[Dict[str, Any]]:
            fl = self._get_feature_layer(layer_url)
            out_statistics = [
                {
                    "statisticType": "count",
                    "onStatisticField": field_name,
                    "outStatisticFieldName": "value_count",
                }
            ]
            fs = fl.query(
                where=where,
                out_statistics=out_statistics,
                group_by_fields_for_statistics=field_name,
                result_record_count=max_values,
            )
            return [
                {
                    "value": f.attributes.get(field_name),
                    "count": f.attributes.get("value_count", 0),
                }
                for f in fs.features
            ]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _query_distinct)

    # ── Buffer geometry ─────────────────────────────────────────────────

    async def buffer_geometry(
        self,
        geometry: Dict[str, Any],
        radius: float,
        unit: str = "feet",
        out_sr: int = 4326,
    ) -> Dict[str, Any]:
        """Buffer a geometry by a given radius.

        Args:
            geometry: ArcGIS JSON geometry dict.
            radius: Buffer distance.
            unit: Distance unit (feet, meters, kilometers, miles).
            out_sr: Output spatial reference WKID.

        Returns:
            Buffered polygon geometry dict.
        """
        self._check_closed()
        from arcgis.geometry import Geometry as ArcGISGeometry, LengthUnits
        from arcgis.geometry.functions import buffer as geo_buffer
        from .geometry import geodesic_buffer_fallback, UNIT_TO_METERS

        _UNIT_MAP = {
            "feet": LengthUnits.FOOT,
            "meters": LengthUnits.METER,
            "kilometers": LengthUnits.KILOMETER,
            "miles": LengthUnits.STATUTEMILE,
        }

        def _buffer() -> Dict[str, Any]:
            try:
                geom = ArcGISGeometry(geometry)
                esri_unit = _UNIT_MAP.get(unit, LengthUnits.METER)
                buffered = geo_buffer(
                    geometries=[geom],
                    distances=[radius],
                    unit=esri_unit,
                    in_sr=geometry.get("spatialReference", {}).get("wkid", 4326),
                    out_sr=out_sr,
                    gis=self._auth.gis,
                )
                if buffered:
                    return dict(buffered[0])
            except Exception:
                logger.warning(
                    "geo_buffer() failed, falling back to geodesic buffer",
                    exc_info=True,
                )
            # Fallback: math-based geodesic buffer
            radius_m = radius * UNIT_TO_METERS.get(unit, 1.0)
            return geodesic_buffer_fallback(geometry, radius_m)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _buffer)

    # ── Union geometries ────────────────────────────────────────────────

    async def union_geometries(
        self,
        geometries: List[Dict[str, Any]],
        spatial_ref: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Union multiple geometries into a single geometry.

        Args:
            geometries: List of ArcGIS JSON geometry dicts.
            spatial_ref: Spatial reference WKID. If None, inferred from the
                first geometry's spatialReference.

        Returns:
            Unified geometry dict, or None if input is empty.
        """
        self._check_closed()

        if not geometries:
            return None

        if len(geometries) == 1:
            return geometries[0]

        from arcgis.geometry import Geometry as ArcGISGeometry
        from arcgis.geometry.functions import union as geo_union

        from .geometry import _fallback_ring_merge

        def _union() -> Optional[Dict[str, Any]]:
            sr = spatial_ref or geometries[0].get(
                "spatialReference", {}
            ).get("wkid", 4326)
            geom_objects = [ArcGISGeometry(g) for g in geometries]
            try:
                result = geo_union(geometries=geom_objects, spatial_ref=sr)
            except Exception:
                logger.warning(
                    "geo_union failed for %d geometries, falling back to ring merge",
                    len(geom_objects),
                    exc_info=True,
                )
                return _fallback_ring_merge(geometries, sr)
            if result is None:
                return None
            if isinstance(result, list):
                return dict(result[0]) if result else None
            return dict(result)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _union)

    # ── Service layers ──────────────────────────────────────────────────

    async def get_service_layers(
        self,
        service_url: str,
    ) -> List[Dict[str, Any]]:
        """Fetch the layer list from a MapServer/FeatureServer REST endpoint.

        Args:
            service_url: ArcGIS Server REST service URL.

        Returns:
            List of layer metadata dicts.
        """
        self._check_closed()
        import json as _json
        import urllib.request

        def _fetch_layers() -> List[Dict[str, Any]]:
            url = service_url.rstrip("/") + "?f=json"
            req = urllib.request.Request(url)
            if self._auth.gis and hasattr(self._auth.gis, "_con"):
                token = getattr(self._auth.gis._con, "token", None)
                if token:
                    url += f"&token={token}"
                    req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self._config.http_timeout if self._config else 30) as resp:
                data = _json.loads(resp.read().decode())
            layers = data.get("layers", [])
            return [
                {
                    "id": lyr.get("id"),
                    "name": lyr.get("name"),
                    "type": lyr.get("type"),
                    "geometry_type": lyr.get("geometryType"),
                    "url": f"{service_url.rstrip('/')}/{lyr.get('id')}",
                    "description": lyr.get("description", ""),
                }
                for lyr in layers
            ]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _fetch_layers)

    # ── Geocoding ───────────────────────────────────────────────────────

    def _get_geocode_service_url(self) -> str:
        """Resolve the geocoding service URL from config or portal properties."""
        # Explicit config takes priority
        url = self._config.geocode_url if self._config else ""
        if url:
            return url.rstrip("/")

        # Discover from portal helper services
        gis = self._auth.gis
        if gis:
            try:
                props = gis.properties
                helper = getattr(props, "helperServices", None)
                if helper:
                    geocode_svcs = getattr(helper, "geocode", None)
                    if geocode_svcs and len(geocode_svcs) > 0:
                        svc_url = getattr(geocode_svcs[0], "url", "")
                        if svc_url:
                            logger.debug("Discovered geocode URL: %s", svc_url)
                            return svc_url.rstrip("/")
            except Exception as e:
                logger.warning("Could not discover geocode service URL: %s", e)

        raise RuntimeError(
            "No geocoding service URL found. Set ARCGIS_GEOCODE_URL env var "
            "or ensure the portal has a geocoding helper service configured."
        )

    def _get_token(self) -> Optional[str]:
        """Get the current GIS token."""
        gis = self._auth.gis
        if gis and hasattr(gis, "_con") and hasattr(gis._con, "token"):
            return gis._con.token
        return None

    # Esri World Geocoding Service URL (public, no token needed for findAddressCandidates)
    _WORLD_GEOCODE_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer"

    async def geocode(
        self,
        address: str,
        max_results: int = 1,
        out_sr: int = 4326,
    ) -> List[Dict[str, Any]]:
        """Geocode an address string to geographic coordinates.

        Uses direct REST calls to the geocoding service, bypassing
        the arcgis SDK's geocode function to avoid service-discovery hangs
        and thread-pool token issues.

        Falls back to the Esri World Geocoding Service if the primary
        (enterprise) geocoder returns zero candidates.

        Args:
            address: Address string to geocode.
            max_results: Maximum number of candidates to return.
            out_sr: Output spatial reference WKID.

        Returns:
            List of candidate dicts with score, address, location, geometry.
        """
        import requests as _requests

        self._check_closed()
        if self._auth.gis is None:
            raise RuntimeError(
                "geocode requires an authenticated GIS instance. "
                "Check ARCGIS_PORTAL_URL and credentials."
            )

        geocode_url = self._get_geocode_service_url()

        def _do_geocode(svc_url: str, use_token: bool = True) -> List[Dict[str, Any]]:
            params: Dict[str, Any] = {
                "SingleLine": address,
                "f": "json",
                "outSR": out_sr,
                "maxLocations": max_results,
                "outFields": "*",
                "matchOutOfRange": "true",
            }
            if use_token:
                token = self._get_token()
                if token:
                    params["token"] = token

            url = f"{svc_url}/findAddressCandidates"
            logger.debug(
                "Geocode request — url=%s params=%s",
                url,
                {k: v for k, v in params.items() if k != "token"},
            )

            resp = _requests.get(
                url,
                params=params,
                verify=self._auth._verify_ssl if use_token else True,
                timeout=self._config.http_timeout if self._config else 30,
            )
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise Exception(str(data["error"]))

            candidates = data.get("candidates", [])
            logger.info(
                "Geocode result — address=%s candidates=%d svc=%s",
                address[:80],
                len(candidates),
                svc_url.split("/")[-1] if "/" in svc_url else svc_url,
            )
            return [
                {
                    "score": c.get("score"),
                    "address": c.get("address"),
                    "location": c.get("location"),
                    "attributes": c.get("attributes", {}),
                    "geometry": c.get("location"),
                }
                for c in candidates
            ]

        def _geocode() -> List[Dict[str, Any]]:
            # Try primary (enterprise) geocoder first
            try:
                candidates = _do_geocode(geocode_url, use_token=True)
                if candidates:
                    return candidates
            except Exception as primary_exc:
                logger.warning(
                    "Primary geocoder failed for address=%s: %s",
                    address[:80],
                    str(primary_exc)[:200],
                )
                candidates = []

            # Fallback to Esri World Geocoding Service
            if geocode_url.rstrip("/") != self._WORLD_GEOCODE_URL:
                logger.info(
                    "Falling back to Esri World Geocoding Service for address=%s",
                    address[:80],
                )
                try:
                    return _do_geocode(self._WORLD_GEOCODE_URL, use_token=False)
                except Exception as fallback_exc:
                    logger.warning(
                        "World Geocoding Service fallback failed: %s",
                        fallback_exc,
                    )

            return candidates

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self._executor, _geocode)
        except Exception as exc:
            if self._is_token_error(exc):
                logger.warning(
                    "Token error in geocode (%s), re-initializing GIS",
                    str(exc)[:100],
                )
                await self._auth.refresh(
                    clear_layer_cache_fn=self._layer_cache.clear
                )
                if self._auth.gis is None:
                    raise RuntimeError(
                        "Re-initialization failed after token error in geocode"
                    ) from exc
                return await loop.run_in_executor(self._executor, _geocode)
            raise

    # ── Reverse geocoding ───────────────────────────────────────────────

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        distance: float = 100,
    ) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address.

        Uses direct REST calls to the geocoding service.

        Args:
            latitude: Latitude (WGS84).
            longitude: Longitude (WGS84).
            distance: Search radius in meters.

        Returns:
            Address dict with formatted address, components, and location.
        """
        import requests as _requests

        self._check_closed()
        if self._auth.gis is None:
            raise RuntimeError(
                "reverse_geocode requires an authenticated GIS instance. "
                "Check ARCGIS_PORTAL_URL and credentials."
            )

        geocode_url = self._get_geocode_service_url()

        def _reverse() -> Dict[str, Any]:
            params: Dict[str, Any] = {
                "location": f"{longitude},{latitude}",
                "distance": distance,
                "f": "json",
            }
            token = self._get_token()
            if token:
                params["token"] = token

            resp = _requests.get(
                f"{geocode_url}/reverseGeocode",
                params=params,
                verify=self._auth._verify_ssl,
                timeout=self._config.http_timeout if self._config else 30,
            )
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise Exception(str(data["error"]))

            addr_obj = data.get("address", {})
            loc_obj = data.get("location", {})
            return {
                "address": addr_obj.get("Match_addr"),
                "location": {"x": loc_obj.get("x", longitude), "y": loc_obj.get("y", latitude)},
                "score": data.get("score"),
                "address_components": addr_obj,
            }

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self._executor, _reverse)
        except Exception as exc:
            if self._is_token_error(exc):
                logger.warning(
                    "Token error in reverse_geocode (%s), re-initializing GIS",
                    str(exc)[:100],
                )
                await self._auth.refresh(
                    clear_layer_cache_fn=self._layer_cache.clear
                )
                if self._auth.gis is None:
                    raise RuntimeError(
                        "Re-initialization failed after token error in reverse_geocode"
                    ) from exc
                return await loop.run_in_executor(self._executor, _reverse)
            raise
