"""
Proximity search tool for ArcGIS feature layers.

Tools: find_nearby
"""

import logging
from typing import Annotated, Any, Dict, List, Optional, Union

from mcp.server.fastmcp import Context
from pydantic import Field

from ..arcgis.client import ArcGISClient
from ..arcgis.geometry import (
    UNIT_TO_METERS,
    compute_distance,
    normalize_geometry,
)
from ._base import ensure_geometry_dict
from ._registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="find_nearby",
    description="Find features near a location, sorted by distance.",
)
async def find_nearby(
    client: ArcGISClient,
    ctx: Context,
    layer_url: Annotated[str, Field(description="Full URL to the ArcGIS feature layer to search")],
    geometry: Annotated[Union[str, dict], Field(description="Input geometry as JSON string or dict (ArcGIS JSON or GeoJSON) — point, polygon, polyline, or multipoint")],
    radius: Annotated[float, Field(description="Search radius")],
    unit: Annotated[str, Field(description="Distance unit: feet, meters, kilometers, or miles")] = "miles",
    where: Annotated[str, Field(description="SQL WHERE clause to filter features")] = "1=1",
    out_fields: Annotated[str, Field(description="Comma-separated field list for returned attributes")] = "*",
    max_results: Annotated[int, Field(description="Maximum number of nearest features to return")] = 20,
) -> Dict[str, Any]:
    """Find features near a geometry, sorted by distance.

    Searches a feature layer for features within a radius of the given
    geometry. Returns features sorted by distance (nearest first), each
    enriched with computed geodesic distance from the input geometry's centroid.
    """
    try:
        geometry_dict = ensure_geometry_dict(geometry)
    except Exception as e:
        return {"error": "Invalid geometry", "detail": str(e)}

    if unit not in UNIT_TO_METERS:
        return {
            "error": "Invalid unit",
            "detail": f"Unit must be one of: {', '.join(UNIT_TO_METERS.keys())}",
        }

    if radius <= 0:
        return {"error": "Invalid radius", "detail": "Radius must be positive"}

    arcgis_geom = normalize_geometry(geometry_dict)

    try:
        await ctx.report_progress(1, 4, message="Creating search area buffer")
        buffered = await client.buffer_geometry(
            geometry=arcgis_geom, radius=radius, unit=unit,
        )

        await ctx.report_progress(2, 4, message="Querying features within radius")
        query_result = await client.query_layer(
            layer_url=layer_url, where=where, out_fields=out_fields,
            geometry=buffered, spatial_rel="esriSpatialRelIntersects",
            return_geometry=True,
        )

        features = query_result.get("features", [])

        await ctx.report_progress(3, 4, message="Computing distances")
        enriched: List[Dict[str, Any]] = []
        for feat in features:
            geom = feat.get("geometry")
            if geom:
                dist = compute_distance(arcgis_geom, geom, unit=unit)
            else:
                dist = None
            enriched.append({
                "attributes": feat.get("attributes", {}),
                "geometry": geom,
                "distance": round(dist, 4) if dist is not None else None,
                "distance_unit": unit,
            })

        enriched.sort(key=lambda f: f["distance"] if f["distance"] is not None else float("inf"))
        enriched = enriched[:max_results]

        await ctx.report_progress(4, 4, message="Results sorted by distance")
        return {
            "features": enriched,
            "count": len(enriched),
            "total_in_radius": len(features),
            "search_radius": radius,
            "search_unit": unit,
            "layer_url": layer_url,
        }
    except Exception as e:
        logger.error("find_nearby error: %s", e, exc_info=True)
        return {"error": "find_nearby failed", "detail": str(e)}
