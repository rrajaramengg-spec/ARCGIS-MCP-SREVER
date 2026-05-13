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
    get_centroid,
    normalize_geometry,
)
from ._base import ensure_geometry_dict
from ._registry import register_tool

logger = logging.getLogger(__name__)


def _create_proximity_lines(
    source_geometry: Dict[str, Any],
    near_features: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Create proximity line features connecting source to each near feature.

    Computes distance from line coordinates (source centroid to target centroid)
    in feet and stores in feature attributes.

    Args:
        source_geometry: Source geometry (ArcGIS JSON).
        near_features: List of near features with geometry and attributes.

    Returns:
        List of line features with geometry and distance attributes.
    """
    source_centroid = get_centroid(source_geometry)
    proximity_lines = []

    for idx, feat in enumerate(near_features):
        target_geom = feat.get("geometry")
        if not target_geom:
            continue

        target_centroid = get_centroid(target_geom)

        # Compute distance in feet
        distance_feet = compute_distance(source_centroid, target_centroid, unit="feet")

        # Create line geometry
        line_geom = {
            "paths": [[[source_centroid["x"], source_centroid["y"]],
                       [target_centroid["x"], target_centroid["y"]]]],
            "spatialReference": source_centroid.get("spatialReference", {"wkid": 4326}),
        }

        # Create line feature with distance in attributes
        proximity_lines.append({
            "geometry": line_geom,
            "attributes": {
                "distance": round(distance_feet, 2),
                "distance_unit": "feet",
                "target_id": idx,
            },
        })

    return proximity_lines


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
    max_results: Annotated[int, Field(description="Maximum number of nearest features to return")] = 10,
) -> Dict[str, Any]:
    """Find features near a geometry, sorted by distance.

    Searches a feature layer for features within a radius of the given
    geometry. Returns a normalized multi-layer response with buffer geometry,
    near features in standard FeatureSet format, and proximity lines with
    distance in feet.
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

        # Sort features by distance (for consistent ordering)
        await ctx.report_progress(3, 4, message="Sorting features by distance")
        source_centroid = get_centroid(arcgis_geom)
        features_with_dist = []
        for feat in features:
            geom = feat.get("geometry")
            if geom:
                dist = compute_distance(source_centroid, geom, unit="feet")
            else:
                dist = float("inf")
            features_with_dist.append((dist, feat))

        features_with_dist.sort(key=lambda x: x[0])
        sorted_features = [feat for _, feat in features_with_dist[:max_results]]

        # Create proximity lines with distance in feet
        proximity_lines = _create_proximity_lines(arcgis_geom, sorted_features)

        await ctx.report_progress(4, 4, message="Response complete")
        return {
            "buffer_geometry": buffered,
            "near_features": sorted_features,
            "proximity_lines": proximity_lines,
            "count": len(sorted_features),
            "total_in_radius": len(features),
            "search_radius": radius,
            "search_unit": unit,
            "layer_url": layer_url,
            "geometryType": query_result.get("geometryType", "esriGeometryPoint"),
            "spatialReference": query_result.get("spatialReference", {"wkid": 4326}),
            "fields": query_result.get("fields", []),
        }
    except Exception as e:
        logger.error("find_nearby error: %s", e, exc_info=True)
        return {"error": "find_nearby failed", "detail": str(e)}
