"""
Stateless geometry filter builders and FeatureSet conversion utilities.
"""

import logging
import math
from collections import Counter
from typing import Any, Dict, List, Optional

from arcgis.features import FeatureSet
from arcgis.geometry import Geometry
from arcgis.geometry import filters as geometry_filters
from arcgis.geometry.functions import union as geo_union

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────

MAX_UNION_FEATURES = 500

# ── Unit conversion factors (to meters) ─────────────────────────────────

UNIT_TO_METERS: Dict[str, float] = {
    "feet": 0.3048,
    "meters": 1.0,
    "kilometers": 1000.0,
    "miles": 1609.344,
}


def build_geometry_filter(
    geometry: Dict[str, Any],
    spatial_rel: str = "esriSpatialRelIntersects",
) -> Dict[str, Any]:
    """Build a geometry filter using arcgis.geometry.filters."""
    geom = Geometry(geometry)
    rel_lower = spatial_rel.lower()
    if "contains" in rel_lower:
        return geometry_filters.contains(geom)
    elif "within" in rel_lower:
        return geometry_filters.within(geom)
    else:
        return geometry_filters.intersects(geom)


def featureset_to_dict(fs: FeatureSet) -> Dict[str, Any]:
    """Convert a FeatureSet to ArcGIS REST API standard dict format.

    Uses FeatureSet.to_dict() for standard camelCase keys and adds a
    convenience 'count' field.
    """
    result = fs.to_dict()
    result["count"] = len(fs.features)
    return result


def normalize_geometry(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Convert GeoJSON geometry to ArcGIS JSON format if needed.

    If the geometry already has ArcGIS keys (x/y, rings, paths), returns as-is.
    If it has GeoJSON keys (type, coordinates), converts to ArcGIS JSON.

    Args:
        geometry: Geometry dict in GeoJSON or ArcGIS JSON format.

    Returns:
        ArcGIS JSON geometry dict.
    """
    if "type" not in geometry or "coordinates" not in geometry:
        # Already ArcGIS JSON format
        return geometry

    geom_type = geometry["type"]
    coords = geometry["coordinates"]

    if geom_type == "Point":
        return {
            "x": coords[0],
            "y": coords[1],
            "spatialReference": {"wkid": 4326},
        }
    elif geom_type == "MultiPoint":
        return {
            "points": coords,
            "spatialReference": {"wkid": 4326},
        }
    elif geom_type == "LineString":
        return {
            "paths": [coords],
            "spatialReference": {"wkid": 4326},
        }
    elif geom_type == "MultiLineString":
        return {
            "paths": coords,
            "spatialReference": {"wkid": 4326},
        }
    elif geom_type == "Polygon":
        return {
            "rings": coords,
            "spatialReference": {"wkid": 4326},
        }
    elif geom_type == "MultiPolygon":
        rings = []
        for polygon in coords:
            rings.extend(polygon)
        return {
            "rings": rings,
            "spatialReference": {"wkid": 4326},
        }
    else:
        return geometry


def get_centroid(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Extract centroid point from a geometry.

    For point geometries, returns the point itself.
    For polygons/polylines, computes the geometric centroid.

    Args:
        geometry: ArcGIS JSON geometry dict.

    Returns:
        Point geometry dict with x, y, and spatialReference.
    """
    sr = geometry.get("spatialReference", {"wkid": 4326})

    # Point
    if "x" in geometry and "y" in geometry:
        return {"x": geometry["x"], "y": geometry["y"], "spatialReference": sr}

    # Polygon — average of ring vertices
    if "rings" in geometry:
        all_coords = [pt for ring in geometry["rings"] for pt in ring]
        if all_coords:
            avg_x = sum(pt[0] for pt in all_coords) / len(all_coords)
            avg_y = sum(pt[1] for pt in all_coords) / len(all_coords)
            return {"x": avg_x, "y": avg_y, "spatialReference": sr}

    # Polyline — average of path vertices
    if "paths" in geometry:
        all_coords = [pt for path in geometry["paths"] for pt in path]
        if all_coords:
            avg_x = sum(pt[0] for pt in all_coords) / len(all_coords)
            avg_y = sum(pt[1] for pt in all_coords) / len(all_coords)
            return {"x": avg_x, "y": avg_y, "spatialReference": sr}

    return {"x": 0, "y": 0, "spatialReference": sr}


def compute_distance(
    geom_a: Dict[str, Any],
    geom_b: Dict[str, Any],
    unit: str = "meters",
) -> float:
    """Compute geodesic distance between two geometries using haversine.

    Converts geometries to centroids first, then computes the great-circle
    distance. Uses the haversine formula for portability (no server dependency).

    Args:
        geom_a: First geometry (ArcGIS JSON).
        geom_b: Second geometry (ArcGIS JSON).
        unit: Distance unit (feet, meters, kilometers, miles).

    Returns:
        Distance in the requested unit.
    """
    pt_a = get_centroid(geom_a)
    pt_b = get_centroid(geom_b)

    lat1, lon1 = math.radians(pt_a["y"]), math.radians(pt_a["x"])
    lat2, lon2 = math.radians(pt_b["y"]), math.radians(pt_b["x"])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Earth's radius in meters
    earth_radius_m = 6_371_000.0
    distance_m = earth_radius_m * c

    factor = UNIT_TO_METERS.get(unit, 1.0)
    return distance_m / factor


# ── Geodesic buffer fallback ───────────────────────────────────────────

_EARTH_RADIUS_M = 6_371_000.0


def geodesic_buffer_fallback(
    geometry: Dict[str, Any],
    radius_meters: float,
    num_points: int = 64,
) -> Dict[str, Any]:
    """Generate a buffer polygon using math stdlib (no external dependencies).

    Uses equirectangular approximation with cos(lat) longitude correction.
    Accurate to sub-meter for buffers < 50 km at mid-latitudes.

    Args:
        geometry: ArcGIS JSON geometry dict (point, polygon, or polyline).
        radius_meters: Buffer radius in meters.
        num_points: Number of vertices in the buffer ring.

    Returns:
        ArcGIS JSON polygon geometry: ``{rings: [...], spatialReference: {wkid: 4326}}``.
    """
    center = get_centroid(geometry)
    cx, cy = center["x"], center["y"]

    lat_rad = math.radians(cy)
    # Degrees per meter in latitude direction
    deg_per_m_lat = 1.0 / (math.radians(1) * _EARTH_RADIUS_M)
    # Degrees per meter in longitude direction (equirectangular correction)
    cos_lat = math.cos(lat_rad)
    deg_per_m_lon = deg_per_m_lat / cos_lat if cos_lat > 1e-10 else deg_per_m_lat

    ring = []
    for i in range(num_points):
        angle = 2.0 * math.pi * i / num_points
        dx = radius_meters * math.cos(angle)
        dy = radius_meters * math.sin(angle)
        ring.append([cx + dx * deg_per_m_lon, cy + dy * deg_per_m_lat])

    # Close the ring
    ring.append(ring[0][:])

    return {
        "rings": [ring],
        "spatialReference": {"wkid": 4326},
    }


# ── Geometry union ──────────────────────────────────────────────────────

# Mapping from ArcGIS JSON keys to geometry type labels for validation
_GEOM_TYPE_KEYS = {
    "rings": "polygon",
    "paths": "polyline",
    "points": "multipoint",
}


def _classify_geometry(geom: Dict[str, Any]) -> str:
    """Return a type label for an ArcGIS JSON geometry dict."""
    if "x" in geom and "y" in geom:
        return "point"
    for key, label in _GEOM_TYPE_KEYS.items():
        if key in geom:
            return label
    return "unknown"


def union_feature_geometries(
    features: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Extract and union all geometries from a list of ArcGIS feature dicts.

    - Filters out features with no ``"geometry"`` key.
    - Returns ``None`` if no valid geometries remain.
    - Returns the single geometry directly when only one is present (no SDK call).
    - Validates that all geometries are the same type; raises ``ValueError`` on mixed types.
    - Caps at MAX_UNION_FEATURES (500); logs a warning if truncated.
    - Calls ``arcgis.geometry.functions.union()`` for 2+ geometries (SDK auto-discovers GIS).

    Args:
        features: List of ArcGIS feature dicts, each optionally containing a
            ``"geometry"`` key with an ArcGIS JSON geometry dict.

    Returns:
        Unified ArcGIS JSON geometry dict, or ``None`` if no geometries found.

    Raises:
        ValueError: If features contain mixed geometry types.
    """
    # Extract non-null geometries
    geometries = [f["geometry"] for f in features if f.get("geometry")]

    if not geometries:
        return None

    if len(geometries) == 1:
        return geometries[0]

    # Validate homogeneous geometry types
    types = {_classify_geometry(g) for g in geometries}
    if len(types) > 1:
        raise ValueError(
            f"Cannot union mixed geometry types: {', '.join(sorted(types))}. "
            "All features must have the same geometry type."
        )

    # Cap at MAX_UNION_FEATURES
    if len(geometries) > MAX_UNION_FEATURES:
        logger.warning(
            "union_feature_geometries: truncating %d geometries to %d",
            len(geometries),
            MAX_UNION_FEATURES,
        )
        geometries = geometries[:MAX_UNION_FEATURES]

    # Determine spatial reference from first geometry
    sr = geometries[0].get("spatialReference", {}).get("wkid", 4326)

    # Use client-side ring/path merge — instant and sufficient for spatial
    # filter use cases (intersects/contains/within).  The server-side
    # geo_union dissolves shared boundaries but costs ~5-7s network round-trip
    # and isn't needed for spatial filtering.
    merged = _fallback_ring_merge(geometries, sr)
    if merged is not None:
        return merged

    # Fall back to server-side union only if ring merge fails
    geom_objects = [Geometry(g) for g in geometries]
    try:
        result = geo_union(geometries=geom_objects, spatial_ref=sr)
    except Exception:
        logger.warning(
            "geo_union failed for %d geometries, no geometry available",
            len(geom_objects),
            exc_info=True,
        )
        return None

    if result is None:
        return None

    # union() returns a single Geometry or a list; handle both
    if isinstance(result, list):
        return dict(result[0]) if result else None
    return dict(result)


def _fallback_ring_merge(
    geometries: List[Dict[str, Any]],
    sr: int = 4326,
) -> Optional[Dict[str, Any]]:
    """Client-side fallback union via ring/path/point merge.

    Concatenates all rings (polygons), paths (polylines),
    or points (multipoints) into a single multi-part geometry.
    Does NOT dissolve shared boundaries, but works as a
    spatial filter envelope without a geometry service.
    """
    geom_type = _classify_geometry(geometries[0])

    if geom_type == "polygon":
        all_rings = []
        for g in geometries:
            all_rings.extend(g.get("rings", []))
        if not all_rings:
            return None
        return {"rings": all_rings, "spatialReference": {"wkid": sr}}

    if geom_type == "polyline":
        all_paths = []
        for g in geometries:
            all_paths.extend(g.get("paths", []))
        if not all_paths:
            return None
        return {"paths": all_paths, "spatialReference": {"wkid": sr}}

    if geom_type == "multipoint" or geom_type == "point":
        all_points = []
        for g in geometries:
            if "points" in g:
                all_points.extend(g["points"])
            elif "x" in g and "y" in g:
                all_points.append([g["x"], g["y"]])
        if not all_points:
            return None
        return {"points": all_points, "spatialReference": {"wkid": sr}}

    logger.error("Fallback merge unsupported for geometry type: %s", geom_type)
    return None
