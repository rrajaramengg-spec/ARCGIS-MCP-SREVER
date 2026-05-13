"""Unit tests for node executor functions and integration tests for graph pipelines."""

import json
from unittest.mock import AsyncMock

import pytest

from core.orchestrator.graph.context import (
    ArtifactType,
    GraphContext,
)
from core.orchestrator.graph.executors import (
    EXECUTOR_MAP,
    _cached_geocode,
    execute_buffer,
    execute_count,
    execute_geocode,
    execute_proximity,
    execute_query,
    execute_spatial_join,
    execute_summarize,
    execute_union,
)
from core.orchestrator.graph.nodes import (
    BufferNode,
    CountNode,
    GeocodeNode,
    ProximityNode,
    QueryNode,
    SpatialJoinNode,
    SummarizeNode,
    UnionNode,
)
from core.orchestrator.graph.resilience import RetryBudget, RetryPolicy
from core.orchestrator.graph.runtime import ExecutionGraph, GraphRuntime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(tool_responses: dict = None) -> GraphContext:
    """Create a GraphContext with a mocked MCP client.

    Args:
        tool_responses: Mapping of tool_name → return value for call_tool.
    """
    mcp = AsyncMock()
    responses = tool_responses or {}

    async def _call_tool(name, args, **kwargs):
        return responses.get(name, {})

    mcp.call_tool = AsyncMock(side_effect=_call_tool)

    return GraphContext(
        correlation_id="test-corr",
        mcp_client=mcp,
        retry_budget=RetryBudget(max_retries=10),
    )


# ---------------------------------------------------------------------------
# EXECUTOR_MAP completeness
# ---------------------------------------------------------------------------


class TestExecutorMap:
    def test_all_types_covered(self):
        expected = {
            "geocode", "query", "buffer", "union",
            "spatial_join", "proximity", "summarize", "count",
        }
        assert set(EXECUTOR_MAP.keys()) == expected


# ---------------------------------------------------------------------------
# Individual executor tests
# ---------------------------------------------------------------------------


class TestExecuteGeocode:
    @pytest.mark.asyncio
    async def test_stores_geometry_from_candidates(self):
        location = {"x": -86.5, "y": 34.7}
        ctx = _make_ctx({
            "geocode": {"candidates": [{"location": location}], "count": 1},
        })
        node = GeocodeNode(node_id="n1", output_artifact="g1", address="Madison County")

        result = await execute_geocode(node, ctx)

        assert result == location
        assert ctx.get("g1") == location
        assert ctx.artifact_meta["g1"].artifact_type == ArtifactType.GEOMETRY

    @pytest.mark.asyncio
    async def test_no_candidates_stores_raw(self):
        raw = {"candidates": [], "count": 0}
        ctx = _make_ctx({"geocode": raw})
        node = GeocodeNode(node_id="n1", output_artifact="g1", address="Nowhere")

        result = await execute_geocode(node, ctx)

        assert ctx.get("g1") == raw


class TestExecuteQuery:
    @pytest.mark.asyncio
    async def test_basic_query(self):
        feature_set = {"features": [{"attributes": {"NAME": "A"}}], "count": 1}
        ctx = _make_ctx({"query_features": feature_set})
        node = QueryNode(
            node_id="n1", output_artifact="f1",
            layer_url="https://example.com/0",
            where="STATUS='ACTIVE'",
        )

        await execute_query(node, ctx)

        assert ctx.get("f1") == feature_set
        ctx.mcp_client.call_tool.assert_called_once()
        call_args = ctx.mcp_client.call_tool.call_args[0]
        assert call_args[0] == "query_features"
        assert call_args[1]["where"] == "STATUS='ACTIVE'"

    @pytest.mark.asyncio
    async def test_query_with_geometry_ref(self):
        ctx = _make_ctx({"query_features": {"features": [], "count": 0}})
        ctx.put("g1", {"x": 1, "y": 2}, ArtifactType.GEOMETRY, "n0")
        node = QueryNode(
            node_id="n1", output_artifact="f1",
            layer_url="https://example.com/0",
            geometry_ref="g1",
        )

        await execute_query(node, ctx)

        call_args = ctx.mcp_client.call_tool.call_args[0][1]
        assert "geometry_filter" in call_args

    @pytest.mark.asyncio
    async def test_query_with_out_fields(self):
        ctx = _make_ctx({"query_features": {"features": [], "count": 0}})
        node = QueryNode(
            node_id="n1", output_artifact="f1",
            layer_url="https://example.com/0",
            out_fields=["NAME", "TYPE"],
        )

        await execute_query(node, ctx)

        call_args = ctx.mcp_client.call_tool.call_args[0][1]
        assert call_args["out_fields"] == "NAME,TYPE"


class TestExecuteBuffer:
    @pytest.mark.asyncio
    async def test_stores_buffer_geometry(self):
        buffer_geom = {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        ctx = _make_ctx({
            "buffer_and_query": {
                "buffer_geometry": buffer_geom,
                "features": [],
                "count": 0,
            },
        })
        ctx.put("g1", {"x": 1, "y": 2}, ArtifactType.GEOMETRY, "n0")
        node = BufferNode(
            node_id="n1", output_artifact="b1",
            geometry_ref="g1", distance=5.0, unit="miles",
        )

        await execute_buffer(node, ctx)

        assert ctx.get("b1") == buffer_geom
        assert ctx.artifact_meta["b1"].artifact_type == ArtifactType.BUFFER_ZONE


class TestExecuteUnion:
    @pytest.mark.asyncio
    async def test_union_polygons(self):
        features = [
            {"geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
            {"geometry": {"rings": [[[1, 0], [2, 0], [2, 1], [1, 0]]]}},
        ]
        ctx = _make_ctx()
        ctx.put("f1", {"features": features}, ArtifactType.FEATURE_SET, "n0")
        node = UnionNode(node_id="n1", output_artifact="u1", features_ref="f1")

        await execute_union(node, ctx)

        merged = ctx.get("u1")
        assert merged is not None
        assert "rings" in merged
        assert len(merged["rings"]) == 2

    @pytest.mark.asyncio
    async def test_union_no_geometries(self):
        ctx = _make_ctx()
        ctx.put("f1", {"features": [{"attributes": {}}]}, ArtifactType.FEATURE_SET, "n0")
        node = UnionNode(node_id="n1", output_artifact="u1", features_ref="f1")

        await execute_union(node, ctx)

        assert ctx.get("u1") is None


class TestExecuteSpatialJoin:
    @pytest.mark.asyncio
    async def test_spatial_join(self):
        feature_set = {"features": [{"attributes": {"NAME": "B"}}], "count": 1}
        ctx = _make_ctx({"query_features": feature_set})
        ctx.put("u1", {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}, ArtifactType.UNION_GEOMETRY, "n0")
        node = SpatialJoinNode(
            node_id="n1", output_artifact="sj1",
            layer_url="https://example.com/0", geometry_ref="u1",
        )

        await execute_spatial_join(node, ctx)

        assert ctx.get("sj1") == feature_set
        call_args = ctx.mcp_client.call_tool.call_args[0][1]
        assert "geometry_filter" in call_args
        assert call_args["spatial_rel"] == "esriSpatialRelIntersects"


class TestExecuteProximity:
    @pytest.mark.asyncio
    async def test_proximity(self):
        result = {"features": [{"attributes": {"NAME": "C"}}], "count": 1}
        ctx = _make_ctx({"find_nearby": result})
        ctx.put("g1", {"x": 1, "y": 2}, ArtifactType.GEOMETRY, "n0")
        node = ProximityNode(
            node_id="n1", output_artifact="p1",
            geometry_ref="g1", layer_url="https://example.com/0",
            distance=10.0, unit="miles",
        )

        await execute_proximity(node, ctx)

        assert ctx.get("p1") == result
        call_args = ctx.mcp_client.call_tool.call_args[0][1]
        assert call_args["radius"] == 10.0
        assert call_args["where"] == "1=1"
        assert "out_fields" not in call_args

    @pytest.mark.asyncio
    async def test_proximity_with_where_filter(self):
        result = {"features": [{"attributes": {"FIBER": "Y"}}], "count": 1}
        ctx = _make_ctx({"find_nearby": result})
        ctx.put("g1", {"x": 1, "y": 2}, ArtifactType.GEOMETRY, "n0")
        node = ProximityNode(
            node_id="n1", output_artifact="p1",
            geometry_ref="g1", layer_url="https://example.com/0",
            distance=200.0, unit="feet", top=5,
            where="FIBER_EQUIP_ATTACHED='Y'",
            out_fields=["NAME", "FIBER_EQUIP_ATTACHED"],
        )

        await execute_proximity(node, ctx)

        call_args = ctx.mcp_client.call_tool.call_args[0][1]
        assert call_args["where"] == "FIBER_EQUIP_ATTACHED='Y'"
        assert call_args["out_fields"] == "NAME,FIBER_EQUIP_ATTACHED"
        assert call_args["max_results"] == 5

    @pytest.mark.asyncio
    async def test_proximity_default_top_is_2000(self):
        ctx = _make_ctx({"find_nearby": {"features": [], "count": 0}})
        ctx.put("g1", {"x": 1, "y": 2}, ArtifactType.GEOMETRY, "n0")
        node = ProximityNode(
            node_id="n1", output_artifact="p1",
            geometry_ref="g1", layer_url="https://example.com/0",
            distance=100.0, unit="meters",
        )

        await execute_proximity(node, ctx)

        call_args = ctx.mcp_client.call_tool.call_args[0][1]
        assert call_args["max_results"] == 2000


class TestExecuteSummarize:
    @pytest.mark.asyncio
    async def test_summarize(self):
        summary = {"field": "POP", "count": 10, "sum": 50000}
        ctx = _make_ctx({"summarize_field": summary})
        ctx.put(
            "f1",
            {"features": [], "layer_url": "https://example.com/0"},
            ArtifactType.FEATURE_SET,
            "n0",
        )
        node = SummarizeNode(
            node_id="n1", output_artifact="s1",
            features_ref="f1", field_name="POP", stat_type="sum",
        )

        await execute_summarize(node, ctx)

        assert ctx.get("s1") == summary


class TestExecuteCount:
    @pytest.mark.asyncio
    async def test_count(self):
        count_result = {"count": 42}
        ctx = _make_ctx({"count_features": count_result})
        node = CountNode(
            node_id="n1", output_artifact="c1",
            layer_url="https://example.com/0", where="STATUS='ACTIVE'",
        )

        await execute_count(node, ctx)

        assert ctx.get("c1") == count_result
        call_args = ctx.mcp_client.call_tool.call_args[0][1]
        assert call_args["where"] == "STATUS='ACTIVE'"


# ---------------------------------------------------------------------------
# Integration: full graph execution with mocked MCP
# ---------------------------------------------------------------------------


class TestGraphIntegrationGeocodeBufferSpatialJoin:
    """geocode → buffer → spatial_join pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        location = {"x": -86.5, "y": 34.7}
        buffer_geom = {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        feature_set = {"features": [{"attributes": {"NAME": "Fire Station"}}], "count": 1}

        mcp = AsyncMock()
        call_count = {"n": 0}

        async def _call_tool(name, args, **kwargs):
            call_count["n"] += 1
            if name == "geocode":
                return {"candidates": [{"location": location}], "count": 1}
            if name == "buffer_and_query":
                return {"buffer_geometry": buffer_geom, "features": [], "count": 0}
            if name == "query_features":
                return feature_set
            return {}

        mcp.call_tool = AsyncMock(side_effect=_call_tool)

        nodes = {
            "n1": GeocodeNode(
                node_id="n1", output_artifact="geom_1", address="Madison County",
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n2": BufferNode(
                node_id="n2", output_artifact="buffer_1",
                geometry_ref="geom_1", distance=5.0, unit="miles",
                depends_on=["n1"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n3": SpatialJoinNode(
                node_id="n3", output_artifact="features_1",
                layer_url="https://example.com/0", geometry_ref="buffer_1",
                depends_on=["n2"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = GraphContext(
            correlation_id="test",
            mcp_client=mcp,
            retry_budget=RetryBudget(max_retries=5),
        )
        runtime = GraphRuntime(executor_map=EXECUTOR_MAP)

        result = await runtime.execute(graph, ctx)

        assert result.errors == {}
        assert len(result.node_timing) == 3
        assert ctx.get("geom_1") == location
        assert ctx.get("buffer_1") == buffer_geom
        assert ctx.get("features_1") == feature_set
        assert call_count["n"] == 3


class TestGraphIntegrationParentUnionSpatialJoin:
    """parent query → union → spatial_join children."""

    @pytest.mark.asyncio
    async def test_parent_union_children(self):
        parent_features = {
            "features": [
                {"attributes": {"NAME": "Zone A"}, "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
                {"attributes": {"NAME": "Zone B"}, "geometry": {"rings": [[[1, 0], [2, 0], [2, 1], [1, 0]]]}},
            ],
            "count": 2,
        }
        child_features = {
            "features": [{"attributes": {"NAME": "School"}}],
            "count": 1,
        }

        mcp = AsyncMock()

        async def _call_tool(name, args, **kwargs):
            if name == "query_features":
                if "geometry_filter" in args:
                    return child_features
                return parent_features
            return {}

        mcp.call_tool = AsyncMock(side_effect=_call_tool)

        nodes = {
            "n1": QueryNode(
                node_id="n1", output_artifact="parent_feat",
                layer_url="https://example.com/zones",
                where="TYPE='ZONE'",
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n2": UnionNode(
                node_id="n2", output_artifact="union_geom",
                features_ref="parent_feat",
                depends_on=["n1"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n3": SpatialJoinNode(
                node_id="n3", output_artifact="child_feat",
                layer_url="https://example.com/schools",
                geometry_ref="union_geom",
                depends_on=["n2"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = GraphContext(
            correlation_id="test",
            mcp_client=mcp,
            retry_budget=RetryBudget(max_retries=5),
        )
        runtime = GraphRuntime(executor_map=EXECUTOR_MAP)

        result = await runtime.execute(graph, ctx)

        assert result.errors == {}
        # Union should have merged 2 polygon geometries.
        union_geom = ctx.get("union_geom")
        assert union_geom is not None
        assert len(union_geom["rings"]) == 2
        # Child query should have used the union as spatial filter.
        assert ctx.get("child_feat") == child_features


# ---------------------------------------------------------------------------
# Geocode cache tests
# ---------------------------------------------------------------------------


class TestGeocodeCache:
    """Tests for geocode result caching via @alru_cache."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        _cached_geocode.cache_clear()
        yield
        _cached_geocode.cache_clear()

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Second call with same address should hit cache (no extra MCP call)."""
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={
            "candidates": [{"location": {"x": -74.0, "y": 40.0}, "score": 100}]
        })

        await _cached_geocode(mcp, "123 Main St")
        await _cached_geocode(mcp, "123 Main St")

        # Only one MCP call despite two invocations
        assert mcp.call_tool.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_miss_different_address(self):
        """Different addresses should each call MCP."""
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={
            "candidates": [{"location": {"x": 0, "y": 0}}]
        })

        await _cached_geocode(mcp, "123 Main St")
        await _cached_geocode(mcp, "456 Oak Ave")

        assert mcp.call_tool.call_count == 2
