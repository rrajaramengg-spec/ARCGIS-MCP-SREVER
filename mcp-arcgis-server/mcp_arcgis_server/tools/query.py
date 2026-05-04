"""
Query and count tools for ArcGIS feature layers.

Tools: query_features, count_features
"""

import logging
from typing import Annotated, Any, Dict, Optional, Union

from mcp.server.fastmcp import Context
from pydantic import Field

from ..arcgis.client import ArcGISClient
from ._base import ensure_geometry_dict
from ._registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="query_features",
    description="Query features from an ArcGIS feature layer. Returns matching features with attributes and optionally geometries.",
)
async def query_features(
    client: ArcGISClient,
    ctx: Context,
    layer_url: Annotated[str, Field(description="Full URL to the ArcGIS feature layer endpoint")],
    where: Annotated[str, Field(description="SQL WHERE clause to filter features")] = "1=1",
    out_fields: Annotated[str, Field(description="Comma-separated list of fields to return, or '*' for all")] = "*",
    return_geometry: Annotated[bool, Field(description="Whether to include geometry in the response")] = True,
    geometry_filter: Annotated[Optional[Union[str, dict]], Field(description="Geometry as JSON string or dict to use as a spatial filter")] = None,
    spatial_rel: Annotated[str, Field(description="Spatial relationship: esriSpatialRelIntersects, esriSpatialRelContains, esriSpatialRelWithin, etc.")] = "esriSpatialRelIntersects",
) -> Dict[str, Any]:
    """Query features from an ArcGIS feature layer.

    Returns a list of matching features with their attributes and optionally geometries.
    Authentication is handled automatically based on the layer URL domain.
    """
    await ctx.report_progress(0, 1, message="Querying layer features")
    geometry = None
    geometry_type = None
    if geometry_filter:
        geometry = ensure_geometry_dict(geometry_filter)
        if "rings" in geometry:
            geometry_type = "esriGeometryPolygon"
        elif "paths" in geometry:
            geometry_type = "esriGeometryPolyline"
        elif "x" in geometry and "y" in geometry:
            geometry_type = "esriGeometryPoint"
        else:
            geometry_type = "esriGeometryEnvelope"

    result = await client.query_layer(
        layer_url=layer_url,
        where=where,
        out_fields=out_fields,
        return_geometry=return_geometry,
        geometry=geometry,
        geometry_type=geometry_type,
        spatial_rel=spatial_rel,
    )
    await ctx.report_progress(1, 1, message="Query complete")
    return result


@register_tool(
    name="count_features",
    description="Count features in an ArcGIS feature layer matching a WHERE clause.",
)
async def count_features(
    client: ArcGISClient,
    ctx: Context,
    layer_url: Annotated[str, Field(description="Full URL to the ArcGIS feature layer endpoint")],
    where: Annotated[str, Field(description="SQL WHERE clause to filter features")] = "1=1",
) -> Dict[str, Any]:
    """Count features in an ArcGIS feature layer matching a WHERE clause.

    Returns the integer count without returning feature data.
    """
    result = await client.query_layer(
        layer_url=layer_url,
        where=where,
        return_count_only=True,
    )
    return {"count": result.get("count", 0)}
