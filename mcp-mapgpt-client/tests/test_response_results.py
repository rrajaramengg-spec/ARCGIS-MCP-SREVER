"""Unit tests for response result helpers: _decompose_proximity, _artifact_to_result.

These module-level functions convert graph artifacts into the typed
``results[]`` shape (2 types: ``feature_set`` + ``geocode``).
"""

import pytest
from types import SimpleNamespace
from core.orchestrator.query_handler import _decompose_proximity, _artifact_to_result
from core.orchestrator.graph.context import ArtifactMeta, ArtifactType


# ── Helpers ────────────────────────────────────────

def _node(node_type="query", layer_url="https://example.com/0"):
    return SimpleNamespace(node_type=node_type, layer_url=layer_url)


def _meta(artifact_type, producer="n1"):
    return ArtifactMeta(producer_node_id=producer, artifact_type=artifact_type)


# ── _decompose_proximity ──────────────────────────


class TestDecomposeProximity:
    """Split find_nearby compound blob into 3 feature_set results."""

    def test_returns_three_entries(self):
        raw = {
            "buffer_geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            "proximity_lines": [
                {"geometry": {"paths": [[[0, 0], [1, 1]]]}, "attributes": {"distance": 500}},
            ],
            "near_features": [
                {"geometry": {"x": 1, "y": 1}, "attributes": {"NAME": "A"}},
            ],
            "count": 1,
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
            "fields": [{"name": "NAME"}],
        }
        node = _node(node_type="proximity", layer_url="https://example.com/0")
        results = _decompose_proximity(raw, node)

        assert len(results) == 3

    def test_buffer_entry(self):
        raw = {
            "buffer_geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            "proximity_lines": [],
            "near_features": [],
            "count": 0,
            "spatialReference": {"wkid": 4326},
        }
        results = _decompose_proximity(raw, _node())
        buf = results[0]

        assert buf["type"] == "feature_set"
        assert buf["role"] == "buffer"
        assert buf["layer"] == "_buffer"
        assert buf["geometryType"] == "esriGeometryPolygon"
        assert len(buf["features"]) == 1
        assert buf["features"][0]["geometry"] == raw["buffer_geometry"]

    def test_distance_line_entry(self):
        lines = [
            {"geometry": {"paths": [[[0, 0], [1, 1]]]}, "attributes": {"distance": 500}},
            {"geometry": {"paths": [[[0, 0], [2, 2]]]}, "attributes": {"distance": 1000}},
        ]
        raw = {
            "buffer_geometry": {},
            "proximity_lines": lines,
            "near_features": [],
            "count": 0,
            "spatialReference": {"wkid": 4326},
        }
        results = _decompose_proximity(raw, _node())
        dist = results[1]

        assert dist["type"] == "feature_set"
        assert dist["role"] == "distance_line"
        assert dist["layer"] == "_distance"
        assert dist["geometryType"] == "esriGeometryPolyline"
        assert dist["features"] == lines
        assert dist["count"] == 2

    def test_result_entry(self):
        features = [{"geometry": {"x": 1, "y": 1}, "attributes": {"NAME": "A"}}]
        raw = {
            "buffer_geometry": {},
            "proximity_lines": [],
            "near_features": features,
            "count": 1,
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
            "fields": [{"name": "NAME"}],
        }
        node = _node(layer_url="https://example.com/0")
        results = _decompose_proximity(raw, node)
        res = results[2]

        assert res["type"] == "feature_set"
        assert res["role"] == "result"
        assert res["layer"] == "https://example.com/0"
        assert res["features"] == features
        assert res["count"] == 1
        assert res["fields"] == [{"name": "NAME"}]

    def test_default_spatial_reference(self):
        raw = {
            "buffer_geometry": {},
            "proximity_lines": [],
            "near_features": [],
            "count": 0,
        }
        results = _decompose_proximity(raw, _node())
        for entry in results:
            assert entry["spatialReference"] == {"wkid": 4326}


# ── _artifact_to_result ───────────────────────────


class TestArtifactToResult:
    """Convert a single graph artifact into a typed result dict."""

    def test_geometry_produces_geocode(self):
        raw = {
            "candidates": [
                {"location": {"x": -75, "y": 40}, "address": "123 Main St", "score": 95},
            ]
        }
        result = _artifact_to_result(raw, _meta(ArtifactType.GEOMETRY), _node())

        assert result["type"] == "geocode"
        assert result["location"] == {"x": -75, "y": 40}
        assert result["address"] == "123 Main St"
        assert result["score"] == 95
        assert result["candidates"] == raw["candidates"]

    def test_geometry_empty_candidates(self):
        raw = {"candidates": []}
        result = _artifact_to_result(raw, _meta(ArtifactType.GEOMETRY), _node())

        assert result["type"] == "geocode"
        assert result["location"] == raw  # falls back to raw
        assert result["address"] == ""
        assert result["score"] == 0

    def test_buffer_zone(self):
        raw = {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]], "spatialReference": {"wkid": 4326}}
        result = _artifact_to_result(raw, _meta(ArtifactType.BUFFER_ZONE), _node())

        assert result["type"] == "feature_set"
        assert result["role"] == "buffer"
        assert result["layer"] == "_buffer"
        assert result["geometryType"] == "esriGeometryPolygon"
        assert len(result["features"]) == 1
        assert result["features"][0]["geometry"] == raw

    def test_buffer_zone_empty_raw(self):
        result = _artifact_to_result({}, _meta(ArtifactType.BUFFER_ZONE), _node())

        assert result["type"] == "feature_set"
        assert result["role"] == "buffer"
        assert result["count"] == 0
        assert result["features"] == []

    def test_count(self):
        raw = {"count": 42}
        node = _node(layer_url="https://example.com/0")
        result = _artifact_to_result(raw, _meta(ArtifactType.COUNT), node)

        assert result["type"] == "feature_set"
        assert result["role"] == "result"
        assert result["count"] == 42
        assert result["features"] == []
        assert result["geometryType"] is None
        assert result["layer"] == "https://example.com/0"

    def test_summary_numeric(self):
        raw = {
            "statistics": {"min": 0, "max": 100, "mean": 50, "std": 20},
            "field": "POPULATION",
            "null_count": 3,
        }
        result = _artifact_to_result(raw, _meta(ArtifactType.SUMMARY), _node())

        assert result["type"] == "feature_set"
        assert result["role"] == "result"
        assert result["layer"] == "POPULATION"
        assert len(result["features"]) == 1
        attrs = result["features"][0]["attributes"]
        assert attrs["min"] == 0
        assert attrs["max"] == 100
        assert attrs["null_count"] == 3

    def test_summary_string_unique_values(self):
        raw = {
            "unique_values": [
                {"value": "A", "count": 10},
                {"value": "B", "count": 5},
            ],
            "field_name": "STATUS",
        }
        result = _artifact_to_result(raw, _meta(ArtifactType.SUMMARY), _node())

        assert result["type"] == "feature_set"
        assert result["role"] == "result"
        assert result["layer"] == "STATUS"
        assert len(result["features"]) == 2
        assert result["features"][0]["attributes"] == {"value": "A", "count": 10}
        assert result["features"][1]["attributes"] == {"value": "B", "count": 5}

    def test_union_geometry(self):
        raw = {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]], "spatialReference": {"wkid": 4326}}
        result = _artifact_to_result(raw, _meta(ArtifactType.UNION_GEOMETRY), _node())

        assert result["type"] == "feature_set"
        assert result["role"] == "source"
        assert result["layer"] == "_union"
        assert result["geometryType"] == "esriGeometryPolygon"

    def test_feature_set_default(self):
        raw = {
            "features": [{"attributes": {"NAME": "A"}, "geometry": {"x": 1, "y": 2}}],
            "count": 1,
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
            "fields": [{"name": "NAME"}],
        }
        node = _node(layer_url="https://example.com/0")
        result = _artifact_to_result(raw, _meta(ArtifactType.FEATURE_SET), node)

        assert result["type"] == "feature_set"
        assert result["role"] == "result"
        assert result["layer"] == "https://example.com/0"
        assert result["features"] == raw["features"]
        assert result["count"] == 1
        assert result["geometryType"] == "esriGeometryPoint"

    def test_feature_set_empty_features(self):
        raw = {"features": [], "count": 0}
        result = _artifact_to_result(raw, _meta(ArtifactType.FEATURE_SET), _node())

        assert result["type"] == "feature_set"
        assert result["role"] == "result"
        assert result["features"] == []
        assert result["count"] == 0

    def test_all_results_have_type_and_role(self):
        """Every ArtifactType produces a result with 'type' field."""
        for at in ArtifactType:
            raw = {"candidates": [{"location": {"x": 0, "y": 0}}]} if at == ArtifactType.GEOMETRY else {}
            result = _artifact_to_result(raw, _meta(at), _node())
            assert "type" in result, f"Missing 'type' for {at}"
            assert result["type"] in ("feature_set", "geocode"), f"Invalid type for {at}: {result['type']}"
