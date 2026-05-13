"""Unit tests for flat DAG intent models — validation, edge cases, serialization."""

import pytest
from pydantic import ValidationError

from core.orchestrator.graph.intent import (
    FlatPlanIntent,
    FlatPlanNode,
    NodeDependency,
)


# ---------------------------------------------------------------------------
# NodeDependency
# ---------------------------------------------------------------------------


class TestNodeDependency:
    def test_minimal(self):
        dep = NodeDependency(node_id="1")
        assert dep.node_id == "1"
        assert dep.join_type is None

    def test_with_join_type(self):
        dep = NodeDependency(node_id="1", join_type="spatial_join")
        assert dep.join_type == "spatial_join"

    def test_from_dict(self):
        dep = NodeDependency.model_validate({"node_id": "1", "join_type": "spatial_join"})
        assert dep.node_id == "1"

    def test_missing_node_id_raises(self):
        with pytest.raises(ValidationError):
            NodeDependency.model_validate({})


# ---------------------------------------------------------------------------
# FlatPlanNode
# ---------------------------------------------------------------------------


class TestFlatPlanNode:
    def test_minimal_where(self):
        node = FlatPlanNode(node_id="1", type="where", layer="COUNTY")
        assert node.node_id == "1"
        assert node.type == "where"
        assert node.depend_on == []
        assert node.intent == ""

    def test_full_where_node(self):
        node = FlatPlanNode(
            node_id="2",
            intent="find PSAP in springfield",
            depend_on=[NodeDependency(node_id="1", join_type="spatial_join")],
            type="where",
            layer="PSAP",
            where="UPPER(NAME) LIKE '%SPRINGFIELD%'",
            out_fields=["NAME", "OBJECTID"],
        )
        assert len(node.depend_on) == 1
        assert node.depend_on[0].join_type == "spatial_join"
        assert node.where == "UPPER(NAME) LIKE '%SPRINGFIELD%'"

    def test_count_node(self):
        node = FlatPlanNode(
            node_id="3",
            type="count",
            layer="ASSET",
            alias="total_assets",
        )
        assert node.alias == "total_assets"
        assert node.type == "count"

    def test_address_node(self):
        node = FlatPlanNode(
            node_id="1",
            type="address",
            address="20 Church Rd, Maple Shade, NJ",
        )
        assert node.address == "20 Church Rd, Maple Shade, NJ"

    def test_location_node(self):
        node = FlatPlanNode(
            node_id="1",
            type="location",
            lon=-74.983,
            lat=39.929,
        )
        assert node.lon == -74.983
        assert node.lat == 39.929

    def test_tool_buffer_node(self):
        node = FlatPlanNode(
            node_id="2",
            type="tool",
            join_type="buffer",
            distance=5000,
            unit="meters",
            depend_on=[NodeDependency(node_id="1")],
        )
        assert node.join_type == "buffer"
        assert node.distance == 5000

    def test_tool_proximity_node(self):
        node = FlatPlanNode(
            node_id="2",
            type="tool",
            join_type="proximity",
            distance=1000,
            unit="meters",
            top=3,
            depend_on=[NodeDependency(node_id="1")],
        )
        assert node.top == 3

    def test_missing_type_raises(self):
        with pytest.raises(ValidationError):
            FlatPlanNode(node_id="1")

    def test_missing_node_id_raises(self):
        with pytest.raises(ValidationError):
            FlatPlanNode(type="where")

    def test_from_dict(self):
        node = FlatPlanNode.model_validate({
            "node_id": "1",
            "intent": "query COUNTY",
            "depend_on": [{"node_id": "0", "join_type": "spatial_join"}],
            "type": "where",
            "layer": "COUNTY",
            "where": "1=1",
        })
        assert node.depend_on[0].join_type == "spatial_join"

    def test_optional_fields_default_none(self):
        node = FlatPlanNode(node_id="1", type="where")
        assert node.layer is None
        assert node.where is None
        assert node.out_fields is None
        assert node.join_type is None
        assert node.distance is None
        assert node.unit is None
        assert node.top is None
        assert node.address is None
        assert node.lon is None
        assert node.lat is None
        assert node.alias is None


# ---------------------------------------------------------------------------
# FlatPlanIntent
# ---------------------------------------------------------------------------


class TestFlatPlanIntent:
    def test_query_intent(self):
        intent = FlatPlanIntent(
            action="query",
            message="Showing results",
            query=[
                FlatPlanNode(node_id="1", type="where", layer="COUNTY"),
            ],
        )
        assert intent.action == "query"
        assert len(intent.query) == 1
        assert intent.locate is None
        assert intent.analyze is None

    def test_locate_intent(self):
        intent = FlatPlanIntent(
            action="locate",
            locate=[
                FlatPlanNode(node_id="1", type="address", address="Test"),
            ],
        )
        assert intent.action == "locate"
        assert len(intent.locate) == 1

    def test_analyze_intent(self):
        intent = FlatPlanIntent(
            action="analyze",
            analyze=[
                FlatPlanNode(node_id="1", type="address", address="Test"),
                FlatPlanNode(
                    node_id="2",
                    type="tool",
                    join_type="buffer",
                    distance=1000,
                    unit="meters",
                    depend_on=[NodeDependency(node_id="1")],
                ),
            ],
        )
        assert len(intent.analyze) == 2

    def test_message_intent(self):
        intent = FlatPlanIntent(action="message", message="Hello")
        assert intent.action == "message"
        assert intent.query is None

    def test_from_full_dict(self):
        """Validate parsing from exact few-shot sample format."""
        raw = {
            "action": "query",
            "query": [
                {
                    "node_id": "1",
                    "intent": "query COUNTY layer to filter for springfield",
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
            "message": "Showing all PSAP in Springfield county",
        }
        intent = FlatPlanIntent.model_validate(raw)
        assert len(intent.query) == 2
        assert intent.query[1].depend_on[0].join_type == "spatial_join"

    def test_missing_action_raises(self):
        with pytest.raises(ValidationError):
            FlatPlanIntent.model_validate({"query": []})

    def test_empty_query_list_valid(self):
        """Empty list is valid at model level — expander rejects it."""
        intent = FlatPlanIntent(action="query", query=[])
        assert intent.query == []

    def test_serialization_roundtrip(self):
        raw = {
            "action": "analyze",
            "analyze": [
                {
                    "node_id": "1",
                    "intent": "geocode",
                    "depend_on": [],
                    "type": "address",
                    "address": "Test Addr",
                },
                {
                    "node_id": "2",
                    "intent": "buffer",
                    "depend_on": [{"node_id": "1"}],
                    "type": "tool",
                    "join_type": "buffer",
                    "distance": 5000.0,
                    "unit": "meters",
                },
            ],
            "message": "Test",
        }
        intent = FlatPlanIntent.model_validate(raw)
        dumped = intent.model_dump(exclude_none=True)
        restored = FlatPlanIntent.model_validate(dumped)
        assert len(restored.analyze) == 2
        assert restored.analyze[1].distance == 5000.0
