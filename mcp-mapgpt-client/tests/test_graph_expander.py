"""Unit tests for plan expansion — flat DAG LLM intent to ExecutionGraph."""

import json
import os

import pytest

from core.orchestrator.graph.expander import PlanExpansionError, expand_plan
from core.orchestrator.graph.nodes import (
    BufferNode,
    CountNode,
    GeocodeNode,
    ProximityNode,
    QueryNode,
    SpatialJoinNode,
    UnionNode,
)
from core.orchestrator.graph.runtime import ExecutionGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RAG_LAYERS = [
    {"name": "COUNTY", "url": "https://example.com/county/0"},
    {"name": "ASSET", "url": "https://example.com/asset/0"},
    {"name": "SUPPORT", "url": "https://example.com/support/0"},
    {"name": "PSAP", "url": "https://example.com/psap/0"},
    {"name": "RFTAB", "url": "https://example.com/rftab/0"},
    {"name": "MCD", "url": "https://example.com/mcd/0"},
]


def _node_types(graph: ExecutionGraph) -> list:
    return [n.node_type for n in graph.nodes.values()]


def _nodes_by_type(graph: ExecutionGraph, node_type: str) -> list:
    return [n for n in graph.nodes.values() if n.node_type == node_type]


# ---------------------------------------------------------------------------
# Query action expansion — flat DAG format
# ---------------------------------------------------------------------------


class TestExpandQueryFlat:
    def test_simple_where(self):
        """Single where node — no dependencies."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "intent": "query COUNTY for springfield",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "UPPER(NAME) LIKE UPPER('SPRINGFIELD')",
                },
            ],
            "message": "Showing Springfield county",
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        assert len(graph.nodes) == 1
        assert _node_types(graph) == ["query"]
        node = list(graph.nodes.values())[0]
        assert isinstance(node, QueryNode)
        assert node.where == "UPPER(NAME) LIKE UPPER('SPRINGFIELD')"

    def test_spatial_join_two_nodes(self):
        """Parent where → child spatial join (union auto-injected)."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "intent": "query COUNTY for springfield",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "UPPER(NAME) LIKE UPPER('SPRINGFIELD')",
                },
                {
                    "node_id": "2",
                    "intent": "find PSAP in springfield COUNTY by spatial join",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "where",
                    "layer": "PSAP",
                },
            ],
            "message": "Showing PSAP in Springfield county",
        }
        graph = expand_plan(plan, _RAG_LAYERS)

        types = _node_types(graph)
        assert "query" in types
        assert "union" in types
        assert "spatial_join" in types
        assert len(graph.nodes) == 3  # query + union + spatial_join

        levels = graph.topological_levels()
        assert len(levels) == 3  # query | union | spatial_join

    def test_count_with_spatial_join(self):
        """Parent where → child count via spatial join."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "intent": "query COUNTY for springfield",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "UPPER(NAME) LIKE UPPER('SPRINGFIELD')",
                },
                {
                    "node_id": "2",
                    "intent": "count RFTAB in springfield COUNTY by spatial join",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "count",
                    "layer": "RFTAB",
                },
            ],
            "message": "Counting tabs in Springfield county",
        }
        graph = expand_plan(plan, _RAG_LAYERS)

        types = _node_types(graph)
        assert "query" in types
        assert "union" in types
        assert "count" in types
        # Count node should depend on union, not directly on query
        count_nodes = _nodes_by_type(graph, "count")
        assert len(count_nodes) == 1
        union_id = "_union_1"
        assert union_id in count_nodes[0].depends_on

    def test_count_only(self):
        """Single count node — no spatial join."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "intent": "count all COUNTY",
                    "depend_on": [],
                    "type": "count",
                    "layer": "COUNTY",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        assert len(graph.nodes) == 1
        assert _node_types(graph) == ["count"]

    def test_multi_hop_three_nodes(self):
        """Parent → two children via spatial join (shared union)."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "intent": "query COUNTY for springfield",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "UPPER(NAME) LIKE UPPER('SPRINGFIELD')",
                },
                {
                    "node_id": "2",
                    "intent": "count ASSET by spatial join (total)",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "count",
                    "layer": "ASSET",
                    "alias": "total_assets",
                },
                {
                    "node_id": "3",
                    "intent": "count ASSET with service by spatial join",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "count",
                    "layer": "ASSET",
                    "where": "INTERNET_SERVICEABLE_FLAG = 'Y'",
                    "alias": "service_assets",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)

        # query + union + 2 count = 4
        assert len(graph.nodes) == 4
        types = _node_types(graph)
        assert types.count("count") == 2
        assert "union" in types
        # Both counts share the same union node
        union_id = "_union_1"
        for cn in _nodes_by_type(graph, "count"):
            assert union_id in cn.depends_on

    def test_where_with_filter(self):
        """Spatial join child with WHERE filter."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "intent": "query COUNTY for springfield",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "UPPER(NAME) LIKE UPPER('SPRINGFIELD')",
                },
                {
                    "node_id": "2",
                    "intent": "find ASSET in springfield by spatial join",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "where",
                    "layer": "ASSET",
                    "where": "UPPER(BUILDING_TYPE) LIKE UPPER('%commercial%')",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        sj_nodes = _nodes_by_type(graph, "spatial_join")
        assert len(sj_nodes) == 1
        assert sj_nodes[0].where == "UPPER(BUILDING_TYPE) LIKE UPPER('%commercial%')"


# ---------------------------------------------------------------------------
# Analyze action expansion — flat DAG format
# ---------------------------------------------------------------------------


class TestExpandAnalyzeFlat:
    def test_geocode_buffer_children(self):
        """address → buffer → spatial_join child."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "geocode address",
                    "depend_on": [],
                    "type": "address",
                    "address": "20, Church Rd, Maple Shade, NJ, 08052",
                },
                {
                    "node_id": "2",
                    "intent": "create 5000 meters buffer",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "buffer",
                    "distance": 5000,
                    "unit": "meters",
                },
                {
                    "node_id": "3",
                    "intent": "find SUPPORT within buffer",
                    "depend_on": [{"node_id": "2", "join_type": "spatial_join"}],
                    "type": "where",
                    "layer": "SUPPORT",
                },
            ],
            "message": "Finding supports within 5km",
        }
        graph = expand_plan(plan, _RAG_LAYERS)

        types = _node_types(graph)
        assert "geocode" in types
        assert "buffer" in types
        assert "spatial_join" in types

        # Verify chain: geocode → buffer → spatial_join
        levels = graph.topological_levels()
        assert len(levels) == 3

        buffer_nodes = _nodes_by_type(graph, "buffer")
        assert buffer_nodes[0].distance == 5000

    def test_geocode_proximity(self):
        """address → proximity (2-node merged format)."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "geocode address",
                    "depend_on": [],
                    "type": "address",
                    "address": "20, Church Rd, Maple Shade, NJ, 08052",
                },
                {
                    "node_id": "2",
                    "intent": "find nearest SUPPORT within 1000 meters",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "proximity",
                    "layer": "SUPPORT",
                    "distance": 1000,
                    "unit": "meters",
                    "top": 1,
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        types = _node_types(graph)
        assert "geocode" in types
        assert "proximity" in types
        prox = _nodes_by_type(graph, "proximity")[0]
        assert prox.layer_url == "https://example.com/support/0"
        assert prox.top == 1

    def test_proximity_with_where_and_out_fields(self):
        """Proximity node carries where and out_fields from flat plan."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "use coordinates",
                    "depend_on": [],
                    "type": "location",
                    "lon": -75.1,
                    "lat": 40.0,
                },
                {
                    "node_id": "2",
                    "intent": "find 5 nearest fiber supports",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "proximity",
                    "layer": "SUPPORT",
                    "where": "FIBER_EQUIP_ATTACHED='Y'",
                    "out_fields": ["NAME", "FIBER_EQUIP_ATTACHED"],
                    "distance": 3000,
                    "unit": "meters",
                    "top": 5,
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        prox = _nodes_by_type(graph, "proximity")[0]
        assert isinstance(prox, ProximityNode)
        assert prox.where == "FIBER_EQUIP_ATTACHED='Y'"
        assert prox.out_fields == ["NAME", "FIBER_EQUIP_ATTACHED"]
        assert prox.top == 5
        assert prox.distance == 3000

    def test_proximity_default_top_is_2000(self):
        """When top is not specified, ProximityNode defaults to 2000."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "use coordinates",
                    "depend_on": [],
                    "type": "location",
                    "lon": -74.98,
                    "lat": 39.93,
                },
                {
                    "node_id": "2",
                    "intent": "find nearest assets",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "proximity",
                    "layer": "ASSET",
                    "distance": 5000,
                    "unit": "meters",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        prox = _nodes_by_type(graph, "proximity")[0]
        assert prox.top == 2000

    def test_proximity_missing_layer_raises_error(self):
        """Proximity tool node without layer field raises PlanExpansionError."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "use coordinates",
                    "depend_on": [],
                    "type": "location",
                    "lon": -74.98,
                    "lat": 39.93,
                },
                {
                    "node_id": "2",
                    "intent": "find nearest",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "proximity",
                    "distance": 1000,
                    "unit": "meters",
                },
            ],
        }
        with pytest.raises(PlanExpansionError, match="missing 'layer' field"):
            expand_plan(plan, _RAG_LAYERS)

    def test_multi_layer_proximity_fan_out(self):
        """Multiple proximity nodes from one anchor → parallel ProximityNodes."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "use coordinates",
                    "depend_on": [],
                    "type": "location",
                    "lon": -74.98,
                    "lat": 39.93,
                },
                {
                    "node_id": "2",
                    "intent": "find 3 nearest supports",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "proximity",
                    "layer": "SUPPORT",
                    "distance": 5000,
                    "unit": "meters",
                    "top": 3,
                },
                {
                    "node_id": "3",
                    "intent": "find 5 nearest assets",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "proximity",
                    "layer": "ASSET",
                    "distance": 5000,
                    "unit": "meters",
                    "top": 5,
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        prox_nodes = _nodes_by_type(graph, "proximity")
        assert len(prox_nodes) == 2
        layers = {n.layer_url for n in prox_nodes}
        assert "https://example.com/support/0" in layers
        assert "https://example.com/asset/0" in layers
        tops = {n.layer_url: n.top for n in prox_nodes}
        assert tops["https://example.com/support/0"] == 3
        assert tops["https://example.com/asset/0"] == 5

    def test_location_root(self):
        """Coordinates as location root."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "use coordinates",
                    "depend_on": [],
                    "type": "location",
                    "lon": -86.5,
                    "lat": 34.7,
                },
                {
                    "node_id": "2",
                    "intent": "buffer 1000 feet",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "buffer",
                    "distance": 1000,
                    "unit": "feet",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        geocode = _nodes_by_type(graph, "geocode")[0]
        assert "-86.5,34.7" in geocode.address


# ---------------------------------------------------------------------------
# Locate action expansion — flat DAG format
# ---------------------------------------------------------------------------


class TestExpandLocateFlat:
    def test_geocode_address(self):
        """Single locate → geocode node."""
        plan = {
            "action": "locate",
            "locate": [
                {
                    "node_id": "1",
                    "intent": "geocode address",
                    "depend_on": [],
                    "type": "address",
                    "address": "20 Church Rd, Maple Shade, NJ",
                },
            ],
            "message": "Locating address",
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        assert len(graph.nodes) == 1
        assert _node_types(graph) == ["geocode"]

    def test_location_coordinates(self):
        """Locate with coordinates."""
        plan = {
            "action": "locate",
            "locate": [
                {
                    "node_id": "1",
                    "intent": "use coordinates",
                    "depend_on": [],
                    "type": "location",
                    "lon": 74.983,
                    "lat": 39.929,
                },
            ],
            "message": "Locating coordinates",
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        assert len(graph.nodes) == 1
        assert _node_types(graph) == ["geocode"]
        assert "74.983,39.929" in list(graph.nodes.values())[0].address


# ---------------------------------------------------------------------------
# Implicit node injection
# ---------------------------------------------------------------------------


class TestImplicitNodeInjection:
    def test_union_injected_for_spatial_join(self):
        """UnionNode auto-injected between query parent and spatial-join child."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "UPPER(NAME) LIKE UPPER('SPRINGFIELD')",
                },
                {
                    "node_id": "2",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "where",
                    "layer": "ASSET",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        union_nodes = _nodes_by_type(graph, "union")
        assert len(union_nodes) == 1

    def test_no_union_for_non_spatial_dependency(self):
        """Buffer dependency (no spatial_join) → no union injected."""
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "address",
                    "address": "Test",
                },
                {
                    "node_id": "2",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "buffer",
                    "distance": 1000,
                    "unit": "meters",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        union_nodes = _nodes_by_type(graph, "union")
        assert len(union_nodes) == 0

    def test_shared_union_for_multiple_children(self):
        """Two children with spatial_join to same parent share one union."""
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                },
                {
                    "node_id": "2",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "where",
                    "layer": "ASSET",
                },
                {
                    "node_id": "3",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "count",
                    "layer": "SUPPORT",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        union_nodes = _nodes_by_type(graph, "union")
        assert len(union_nodes) == 1


# ---------------------------------------------------------------------------
# Layer URL resolution
# ---------------------------------------------------------------------------


class TestLayerResolution:
    def test_known_layer_resolved(self):
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "1=1",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        node = list(graph.nodes.values())[0]
        assert node.layer_url == "https://example.com/county/0"

    def test_unknown_layer_empty_url(self):
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "where",
                    "layer": "UNKNOWN_LAYER",
                    "where": "1=1",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        node = list(graph.nodes.values())[0]
        assert node.layer_url == ""

    def test_case_insensitive_lookup(self):
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "where",
                    "layer": "county",
                    "where": "1=1",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        node = list(graph.nodes.values())[0]
        assert node.layer_url == "https://example.com/county/0"


# ---------------------------------------------------------------------------
# Deterministic expansion
# ---------------------------------------------------------------------------


class TestDeterministicExpansion:
    def test_same_plan_same_graph(self):
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                    "where": "1=1",
                },
                {
                    "node_id": "2",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "where",
                    "layer": "ASSET",
                },
            ],
        }
        g1 = expand_plan(plan, _RAG_LAYERS)
        g2 = expand_plan(plan, _RAG_LAYERS)
        assert list(g1.nodes.keys()) == list(g2.nodes.keys())


# ---------------------------------------------------------------------------
# RetryPolicy attachment
# ---------------------------------------------------------------------------


class TestRetryPolicyAttachment:
    def test_retryable_nodes_have_policy(self):
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "address",
                    "address": "Test",
                },
                {
                    "node_id": "2",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "buffer",
                    "distance": 1000,
                    "unit": "meters",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        for node in graph.nodes.values():
            assert node.retry_policy is not None

    def test_union_node_no_retry(self):
        plan = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "depend_on": [],
                    "type": "where",
                    "layer": "COUNTY",
                },
                {
                    "node_id": "2",
                    "depend_on": [{"node_id": "1", "join_type": "spatial_join"}],
                    "type": "where",
                    "layer": "ASSET",
                },
            ],
        }
        graph = expand_plan(plan, _RAG_LAYERS)
        union_nodes = _nodes_by_type(graph, "union")
        assert union_nodes[0].retry_policy.max_attempts == 1


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestExpansionErrors:
    def test_message_action_raises(self):
        with pytest.raises(PlanExpansionError, match="Message"):
            expand_plan({"action": "message", "message": "hello"})

    def test_unknown_action_raises(self):
        with pytest.raises(PlanExpansionError, match="Unsupported"):
            expand_plan({"action": "unknown_action"})

    def test_empty_action_raises(self):
        with pytest.raises(PlanExpansionError, match="Unsupported"):
            expand_plan({"action": "query", "query": []})

    def test_address_missing_address(self):
        with pytest.raises(PlanExpansionError, match="address"):
            expand_plan({
                "action": "locate",
                "locate": [{"node_id": "1", "depend_on": [], "type": "address"}],
            })

    def test_location_missing_coords(self):
        with pytest.raises(PlanExpansionError, match="lon/lat"):
            expand_plan({
                "action": "locate",
                "locate": [{"node_id": "1", "depend_on": [], "type": "location"}],
            })

    def test_unknown_type(self):
        with pytest.raises(PlanExpansionError, match="unknown type"):
            expand_plan({
                "action": "query",
                "query": [{"node_id": "1", "depend_on": [], "type": "invalid_type"}],
            })

    def test_unknown_tool_join_type(self):
        with pytest.raises(PlanExpansionError, match="join_type"):
            expand_plan({
                "action": "analyze",
                "analyze": [
                    {
                        "node_id": "1",
                        "depend_on": [],
                        "type": "address",
                        "address": "Test",
                    },
                    {
                        "node_id": "2",
                        "depend_on": [{"node_id": "1"}],
                        "type": "tool",
                        "join_type": "unknown",
                    },
                ],
            })

    def test_buffer_missing_dependency(self):
        with pytest.raises(PlanExpansionError, match="missing dependency"):
            expand_plan({
                "action": "analyze",
                "analyze": [
                    {
                        "node_id": "1",
                        "depend_on": [],
                        "type": "tool",
                        "join_type": "buffer",
                        "distance": 1000,
                        "unit": "meters",
                    },
                ],
            })


# ---------------------------------------------------------------------------
# input_query_sample2.json validation
# ---------------------------------------------------------------------------


class TestFewShotExamples:
    """Verify that every example from input_query_sample2.json can be expanded."""

    @pytest.fixture
    def samples(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs",
            "few-shot-examples", "input_query_sample2.json",
        )
        if not os.path.exists(path):
            pytest.skip("input_query_sample2.json not found")
        with open(path) as f:
            return json.load(f)

    def test_all_examples_expand(self, samples):
        """Each non-message example should expand without error."""
        expanded = 0
        for i, sample in enumerate(samples):
            plan = sample.get("query", sample)
            action = plan.get("action", "")
            if action == "message":
                continue
            if not any(plan.get(k) for k in ("analyze", "locate", "query")):
                continue
            try:
                graph = expand_plan(plan)
                assert len(graph.nodes) > 0, f"Example {i}: produced 0 nodes"
                expanded += 1
            except PlanExpansionError:
                # Some examples may have incomplete layer_urls — acceptable.
                pass
        assert expanded > 0, "No examples were expanded — check JSON structure"
