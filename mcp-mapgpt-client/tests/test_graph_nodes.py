"""Unit tests for typed spatial execution node models."""

import pytest
from pydantic import TypeAdapter, ValidationError

from core.orchestrator.graph.nodes import (
    BaseNode,
    BufferNode,
    CountNode,
    GeocodeNode,
    ProximityNode,
    QueryNode,
    SpatialJoinNode,
    SummarizeNode,
    TypedNode,
    UnionNode,
)
from core.orchestrator.graph.resilience import RetryPolicy


# Adapter for discriminated union deserialization.
_typed_node_adapter = TypeAdapter(TypedNode)


# ---------------------------------------------------------------------------
# BaseNode defaults
# ---------------------------------------------------------------------------


class TestBaseNode:
    def test_common_fields(self):
        node = GeocodeNode(
            node_id="n1", output_artifact="geom_1", address="Madison County"
        )
        assert node.node_id == "n1"
        assert node.node_type == "geocode"
        assert node.output_artifact == "geom_1"
        assert node.depends_on == []
        assert node.retry_policy is None

    def test_depends_on(self):
        node = QueryNode(
            node_id="n2",
            output_artifact="feat_1",
            layer_url="https://example.com/0",
            depends_on=["n1"],
        )
        assert node.depends_on == ["n1"]

    def test_retry_policy_attachment(self):
        policy = RetryPolicy(max_attempts=5, base_delay=2.0)
        node = GeocodeNode(
            node_id="n1",
            output_artifact="g1",
            address="test",
            retry_policy=policy,
        )
        assert node.retry_policy is not None
        assert node.retry_policy.max_attempts == 5


# ---------------------------------------------------------------------------
# Discriminated union — validation / discrimination
# ---------------------------------------------------------------------------


class TestTypedNodeDiscrimination:
    def test_geocode(self):
        data = {
            "node_id": "n1",
            "node_type": "geocode",
            "output_artifact": "g1",
            "address": "Main St",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, GeocodeNode)
        assert node.address == "Main St"

    def test_query(self):
        data = {
            "node_id": "n2",
            "node_type": "query",
            "output_artifact": "f1",
            "layer_url": "https://example.com/0",
            "where": "STATUS='ACTIVE'",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, QueryNode)

    def test_buffer(self):
        data = {
            "node_id": "n3",
            "node_type": "buffer",
            "output_artifact": "b1",
            "geometry_ref": "g1",
            "distance": 5.0,
            "unit": "miles",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, BufferNode)

    def test_union(self):
        data = {
            "node_id": "n4",
            "node_type": "union",
            "output_artifact": "u1",
            "features_ref": "f1",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, UnionNode)

    def test_spatial_join(self):
        data = {
            "node_id": "n5",
            "node_type": "spatial_join",
            "output_artifact": "sj1",
            "layer_url": "https://example.com/1",
            "geometry_ref": "u1",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, SpatialJoinNode)
        assert node.spatial_rel == "esriSpatialRelIntersects"

    def test_proximity(self):
        data = {
            "node_id": "n6",
            "node_type": "proximity",
            "output_artifact": "p1",
            "geometry_ref": "g1",
            "layer_url": "https://example.com/2",
            "distance": 10.0,
            "unit": "kilometers",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, ProximityNode)

    def test_summarize(self):
        data = {
            "node_id": "n7",
            "node_type": "summarize",
            "output_artifact": "s1",
            "features_ref": "f1",
            "field_name": "POPULATION",
            "stat_type": "sum",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, SummarizeNode)

    def test_count(self):
        data = {
            "node_id": "n8",
            "node_type": "count",
            "output_artifact": "c1",
            "layer_url": "https://example.com/3",
        }
        node = _typed_node_adapter.validate_python(data)
        assert isinstance(node, CountNode)


# ---------------------------------------------------------------------------
# Invalid / edge cases
# ---------------------------------------------------------------------------


class TestTypedNodeErrors:
    def test_unknown_type_rejected(self):
        data = {
            "node_id": "n1",
            "node_type": "unknown_op",
            "output_artifact": "x",
        }
        with pytest.raises(ValidationError):
            _typed_node_adapter.validate_python(data)

    def test_geocode_missing_address(self):
        data = {
            "node_id": "n1",
            "node_type": "geocode",
            "output_artifact": "g1",
        }
        with pytest.raises(ValidationError, match="address"):
            _typed_node_adapter.validate_python(data)

    def test_buffer_zero_distance(self):
        data = {
            "node_id": "n1",
            "node_type": "buffer",
            "output_artifact": "b1",
            "geometry_ref": "g1",
            "distance": 0,
            "unit": "miles",
        }
        with pytest.raises(ValidationError, match="distance"):
            _typed_node_adapter.validate_python(data)

    def test_buffer_negative_distance(self):
        data = {
            "node_id": "n1",
            "node_type": "buffer",
            "output_artifact": "b1",
            "geometry_ref": "g1",
            "distance": -1,
            "unit": "miles",
        }
        with pytest.raises(ValidationError):
            _typed_node_adapter.validate_python(data)

    def test_proximity_zero_distance(self):
        data = {
            "node_id": "n1",
            "node_type": "proximity",
            "output_artifact": "p1",
            "geometry_ref": "g1",
            "layer_url": "https://example.com/0",
            "distance": 0,
            "unit": "miles",
        }
        with pytest.raises(ValidationError):
            _typed_node_adapter.validate_python(data)


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestTypedNodeSerialization:
    def test_round_trip(self):
        node = GeocodeNode(
            node_id="n1", output_artifact="g1", address="Test Addr"
        )
        data = node.model_dump()
        assert data["node_type"] == "geocode"
        restored = _typed_node_adapter.validate_python(data)
        assert isinstance(restored, GeocodeNode)
        assert restored.address == "Test Addr"

    def test_query_node_optional_fields(self):
        node = QueryNode(
            node_id="n1",
            output_artifact="f1",
            layer_url="https://example.com/0",
        )
        data = node.model_dump()
        assert data["where"] is None
        assert data["geometry_ref"] is None
        assert data["out_fields"] is None
