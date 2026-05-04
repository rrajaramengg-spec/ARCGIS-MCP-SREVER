"""
Buffer geometry tool for ArcGIS feature layers.

Tools: buffer_and_query
"""

import logging
from typing import Annotated, Any, Dict, Optional, Union

from mcp.server.fastmcp import Context
from pydantic import Field

from ..arcgis.client import ArcGISClient
from ..arcgis.geometry import UNIT_TO_METERS, normalize_geometry
from ._base import ensure_geometry_dict
from ._registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="buffer_and_query",
    description="Create a buffer zone around a geometry and optionally find features within it.",
)
async def buffer_and_query(
    client: ArcGISClient,
    ctx: Context,
    geometry: Annotated[Union[str, dict], Field(description="Input geometry as JSON string or dict (ArcGIS JSON or GeoJSON)")],
    radius: Annotated[float, Field(description="Buffer distance")],
    unit: Annotated[str, Field(description="Distance unit: feet, meters, kilometers, or miles")] = "feet",
    layer_url: Annotated[Optional[str], Field(description="Feature layer URL to query features within the buffer")] = None,
    where: Annotated[str, Field(description="SQL WHERE clause to filter features (only used with layer_url)")] = "1=1",
    out_fields: Annotated[str, Field(description="Comma-separated field list for query results (only used with layer_url)")] = "*",
) -> Dict[str, Any]:
    """Create a buffer zone around a geometry and optionally find features within it.

    Generates a buffered polygon from the input geometry at the specified distance.
    If layer_url is provided, queries that layer for features intersecting the buffer.
    Accepts both ArcGIS JSON and GeoJSON geometry formats.
    """
    try:
        geom_dict = ensure_geometry_dict(geometry)
    except Exception as e:
        return {"error": "Invalid geometry", "detail": str(e)}

    if unit not in UNIT_TO_METERS:
        return {
            "error": "Invalid unit",
            "detail": f"Unit must be one of: {', '.join(UNIT_TO_METERS.keys())}",
        }

    if radius <= 0:
        return {"error": "Invalid radius", "detail": "Radius must be positive"}

    arcgis_geom = normalize_geometry(geom_dict)

    total_steps = 3 if layer_url else 2
    try:
        await ctx.report_progress(1, total_steps, message="Creating buffer zone")
        buffered = await client.buffer_geometry(
            geometry=arcgis_geom, radius=radius, unit=unit,
        )

        result: Dict[str, Any] = {
            "buffer_geometry": buffered, "radius": radius, "unit": unit,
        }

        if layer_url:
            await ctx.report_progress(2, total_steps, message="Querying features in buffer")
            query_result = await client.query_layer(
                layer_url=layer_url, where=where, out_fields=out_fields,
                geometry=buffered, spatial_rel="esriSpatialRelIntersects",
                return_geometry=True,
            )
            features = query_result.get("features", [])
            result["features"] = features
            result["count"] = len(features)
            result["layer_url"] = layer_url

        await ctx.report_progress(total_steps, total_steps, message="Buffer complete")
        return result
    except Exception as e:
        logger.error("buffer_and_query error: %s", e, exc_info=True)
        return {"error": "buffer_and_query failed", "detail": str(e)}
