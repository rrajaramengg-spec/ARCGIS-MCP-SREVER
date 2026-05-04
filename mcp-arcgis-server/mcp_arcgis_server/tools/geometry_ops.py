"""
Geometry operation tools for ArcGIS feature layers.

Tools: union_geometries
"""

import json
import logging
from typing import Annotated, Any, Dict, List, Union

from pydantic import Field

from ..arcgis.client import ArcGISClient
from ._base import ensure_geometry_dict
from ._registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="union_geometries",
    description=(
        "Union multiple geometries into a single unified geometry. "
        "Use this tool for edge cases like combining geometries from different layers "
        "or sources. For standard parent-child spatial queries, use execute_query_plan "
        "or spatial_join_query instead — they union boundary geometries automatically."
    ),
)
async def union_geometries(
    client: ArcGISClient,
    geometries: Annotated[Union[str, list], Field(description=(
        "JSON string or list of ArcGIS JSON geometry dicts to union. "
        'Example: [{"rings": [...], "spatialReference": {"wkid": 4326}}, ...]'
    ))],
) -> Dict[str, Any]:
    """Union multiple geometries into a single unified geometry.

    Parses the JSON input, delegates to client.union_geometries(), and returns
    the unified geometry or an error dict.
    """
    if isinstance(geometries, list):
        geom_list = geometries
    elif isinstance(geometries, str):
        try:
            geom_list = json.loads(geometries)
        except (json.JSONDecodeError, TypeError) as e:
            return {"error": "Invalid geometry JSON", "detail": str(e)}
    else:
        return {"error": "Invalid geometry input", "detail": f"Expected str or list, got {type(geometries).__name__}"}

    if not isinstance(geom_list, list):
        return {"error": "Invalid geometry JSON", "detail": "Expected a JSON array of geometries"}

    if not geom_list:
        return {"error": "No geometries provided"}

    result = await client.union_geometries(geom_list)

    if result is None:
        return {"error": "Union produced no result"}

    return {"geometry": result}
