"""Node executor functions for graph runtime.

Each function maps a typed node to one or more MCP tool calls,
stores the result in ``GraphContext``, and returns it.

Pattern: ``execute_{node_type}(node, ctx) -> result_data``
"""

import json
import logging
from typing import Any, Callable, Dict

from async_lru import alru_cache

from .context import ArtifactType, GraphContext
from .results import (
    BufferResult,
    CountResult,
    FeatureSetResult,
    GeocodeResult,
    SummaryResult,
)
from core.tool_names import (
    BUFFER_AND_QUERY,
    COUNT_FEATURES,
    FIND_NEARBY,
    GEOCODE,
    QUERY_FEATURES,
    SUMMARIZE_FIELD,
)
from .geometry_utils import union_feature_geometries
from .nodes import (
    BufferNode,
    CountNode,
    GeocodeNode,
    ProximityNode,
    QueryNode,
    SpatialJoinNode,
    SummarizeNode,
    UnionNode,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------


@alru_cache(ttl=3600)
async def _cached_geocode(mcp_client, address: str) -> Any:
    """Cache geocode results for 1 hour to avoid redundant API calls."""
    return await mcp_client.call_tool(GEOCODE, {"address": address})


# ---------------------------------------------------------------------------
# Individual executors
# ---------------------------------------------------------------------------


async def execute_geocode(node: GeocodeNode, ctx: GraphContext) -> Any:
    """Geocode an address → GEOMETRY artifact."""
    result = await _cached_geocode(ctx.mcp_client, node.address)
    if isinstance(result, dict):
        GeocodeResult.model_validate(result)
    # Extract the top candidate's location as the geometry.
    geometry = None
    if isinstance(result, dict):
        candidates = result.get("candidates", [])
        if candidates:
            geometry = candidates[0].get("location", candidates[0].get("geometry"))
    ctx.put(node.output_artifact, geometry or result, ArtifactType.GEOMETRY, node.node_id)
    return geometry or result


async def execute_query(node: QueryNode, ctx: GraphContext) -> Any:
    """Query features with optional spatial filter → FEATURE_SET artifact."""
    args: Dict[str, Any] = {
        "layer_url": node.layer_url,
        "where": node.where or "1=1",
    }
    if node.out_fields:
        args["out_fields"] = ",".join(node.out_fields)
    if node.geometry_ref:
        geometry = ctx.get(node.geometry_ref)
        args["geometry_filter"] = (
            json.dumps(geometry) if isinstance(geometry, dict) else geometry
        )
    result = await ctx.mcp_client.call_tool(QUERY_FEATURES, args)
    if isinstance(result, dict):
        FeatureSetResult.model_validate(result)
    ctx.put(node.output_artifact, result, ArtifactType.FEATURE_SET, node.node_id)
    return result


async def execute_buffer(node: BufferNode, ctx: GraphContext) -> Any:
    """Create a buffer around a geometry → BUFFER_ZONE artifact."""
    geometry = ctx.get(node.geometry_ref)
    args: Dict[str, Any] = {
        "geometry": json.dumps(geometry) if isinstance(geometry, dict) else geometry,
        "radius": node.distance,
        "unit": node.unit,
    }
    result = await ctx.mcp_client.call_tool(BUFFER_AND_QUERY, args)
    # Extract the buffer geometry for downstream use.
    buffer_geom = result
    if isinstance(result, dict) and "buffer_geometry" in result:
        BufferResult.model_validate(result)
        buffer_geom = result["buffer_geometry"]
    ctx.put(node.output_artifact, buffer_geom, ArtifactType.BUFFER_ZONE, node.node_id)
    return buffer_geom


async def execute_union(node: UnionNode, ctx: GraphContext) -> Any:
    """Union geometries from a feature set → UNION_GEOMETRY artifact.

    Uses the duplicated pure-computation utility — no MCP call.
    """
    features_data = ctx.get(node.features_ref)
    features = []
    if isinstance(features_data, dict):
        features = features_data.get("features", [])
    elif isinstance(features_data, list):
        features = features_data

    merged = union_feature_geometries(features)
    ctx.put(node.output_artifact, merged, ArtifactType.UNION_GEOMETRY, node.node_id)
    return merged


async def execute_spatial_join(node: SpatialJoinNode, ctx: GraphContext) -> Any:
    """Query features using a geometry as spatial filter → FEATURE_SET."""
    geometry = ctx.get(node.geometry_ref)
    args: Dict[str, Any] = {
        "layer_url": node.layer_url,
        "geometry_filter": json.dumps(geometry) if isinstance(geometry, dict) else geometry,
        "spatial_rel": node.spatial_rel,
        "where": node.where or "1=1",
    }
    if node.out_fields:
        args["out_fields"] = ",".join(node.out_fields)
    result = await ctx.mcp_client.call_tool(QUERY_FEATURES, args)
    if isinstance(result, dict):
        FeatureSetResult.model_validate(result)
    ctx.put(node.output_artifact, result, ArtifactType.FEATURE_SET, node.node_id)
    return result


async def execute_proximity(node: ProximityNode, ctx: GraphContext) -> Any:
    """Find features near a geometry → FEATURE_SET artifact."""
    geometry = ctx.get(node.geometry_ref)
    args: Dict[str, Any] = {
        "layer_url": node.layer_url,
        "geometry": json.dumps(geometry) if isinstance(geometry, dict) else geometry,
        "radius": node.distance,
        "unit": node.unit,
        "max_results": node.top,
        "where": node.where or "1=1",
    }
    if node.out_fields:
        args["out_fields"] = ",".join(node.out_fields)
    result = await ctx.mcp_client.call_tool(FIND_NEARBY, args)
    if isinstance(result, dict):
        FeatureSetResult.model_validate(result)
    ctx.put(node.output_artifact, result, ArtifactType.FEATURE_SET, node.node_id)
    return result


async def execute_summarize(node: SummarizeNode, ctx: GraphContext) -> Any:
    """Compute field statistics → SUMMARY artifact."""
    features_data = ctx.get(node.features_ref)
    # Derive layer_url from the features artifact if available.
    layer_url = ""
    if isinstance(features_data, dict):
        layer_url = features_data.get("layer_url", "")
    args: Dict[str, Any] = {
        "layer_url": layer_url,
        "field_name": node.field_name,
        "statistics": node.stat_type,
    }
    result = await ctx.mcp_client.call_tool(SUMMARIZE_FIELD, args)
    if isinstance(result, dict):
        SummaryResult.model_validate(result)
    ctx.put(node.output_artifact, result, ArtifactType.SUMMARY, node.node_id)
    return result


async def execute_count(node: CountNode, ctx: GraphContext) -> Any:
    """Count features → COUNT artifact."""
    args: Dict[str, Any] = {
        "layer_url": node.layer_url,
        "where": node.where or "1=1",
    }
    result = await ctx.mcp_client.call_tool(COUNT_FEATURES, args)
    if isinstance(result, dict):
        CountResult.model_validate(result)
    ctx.put(node.output_artifact, result, ArtifactType.COUNT, node.node_id)
    return result


# ---------------------------------------------------------------------------
# Executor map — node_type → executor function
# ---------------------------------------------------------------------------

EXECUTOR_MAP: Dict[str, Callable] = {
    "geocode": execute_geocode,
    "query": execute_query,
    "buffer": execute_buffer,
    "union": execute_union,
    "spatial_join": execute_spatial_join,
    "proximity": execute_proximity,
    "summarize": execute_summarize,
    "count": execute_count,
}
