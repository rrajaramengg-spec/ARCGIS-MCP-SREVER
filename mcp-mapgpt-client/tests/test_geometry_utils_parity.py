"""Parity test: geometry_utils copy vs canonical mcp_arcgis_server version.

Ensures the duplicated pure-computation functions produce identical output.
"""

import sys
import os

import pytest

from core.orchestrator.graph.geometry_utils import (
    _classify_geometry as client_classify,
    _fallback_ring_merge as client_merge,
    union_feature_geometries as client_union,
)

# Import canonical version from mcp-arcgis-server (sibling package).
_server_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "mcp-arcgis-server",
)
sys.path.insert(0, os.path.abspath(_server_path))

from mcp_arcgis_server.arcgis.geometry import (  # noqa: E402
    _classify_geometry as server_classify,
    _fallback_ring_merge as server_merge,
    union_feature_geometries as server_union,
)


# ---------------------------------------------------------------------------
# Test geometries
# ---------------------------------------------------------------------------

POLYGON_A = {"rings": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
POLYGON_B = {"rings": [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]]}
POLYLINE_A = {"paths": [[[0, 0], [1, 1]]]}
POLYLINE_B = {"paths": [[[2, 2], [3, 3]]]}
POINT_A = {"x": 1.0, "y": 2.0}
POINT_B = {"x": 3.0, "y": 4.0}
MULTIPOINT = {"points": [[1, 2], [3, 4]]}


# ---------------------------------------------------------------------------
# _classify_geometry parity
# ---------------------------------------------------------------------------


class TestClassifyGeometryParity:
    @pytest.mark.parametrize("geom,expected", [
        (POLYGON_A, "polygon"),
        (POLYLINE_A, "polyline"),
        (POINT_A, "point"),
        (MULTIPOINT, "multipoint"),
        ({}, "unknown"),
    ])
    def test_classify(self, geom, expected):
        assert client_classify(geom) == server_classify(geom) == expected


# ---------------------------------------------------------------------------
# _fallback_ring_merge parity
# ---------------------------------------------------------------------------


class TestFallbackRingMergeParity:
    def test_polygon_merge(self):
        client_result = client_merge([POLYGON_A, POLYGON_B])
        server_result = server_merge([POLYGON_A, POLYGON_B])
        assert client_result == server_result

    def test_polyline_merge(self):
        client_result = client_merge([POLYLINE_A, POLYLINE_B])
        server_result = server_merge([POLYLINE_A, POLYLINE_B])
        assert client_result == server_result

    def test_point_merge(self):
        client_result = client_merge([POINT_A, POINT_B])
        server_result = server_merge([POINT_A, POINT_B])
        assert client_result == server_result


# ---------------------------------------------------------------------------
# union_feature_geometries parity
# ---------------------------------------------------------------------------


class TestUnionFeatureGeometriesParity:
    def test_single_geometry(self):
        features = [{"geometry": POLYGON_A}]
        assert client_union(features) == server_union(features)

    def test_two_polygons(self):
        features = [
            {"geometry": POLYGON_A},
            {"geometry": POLYGON_B},
        ]
        # Both should use ring merge for 2 polygons.
        client_result = client_union(features)
        server_result = server_union(features)
        assert client_result == server_result

    def test_no_geometries(self):
        features = [{"attributes": {"NAME": "A"}}]
        assert client_union(features) == server_union(features) is None

    def test_empty_list(self):
        assert client_union([]) == server_union([]) is None

    def test_mixed_types_raises(self):
        features = [
            {"geometry": POLYGON_A},
            {"geometry": POINT_A},
        ]
        with pytest.raises(ValueError, match="mixed"):
            client_union(features)
        with pytest.raises(ValueError, match="mixed"):
            server_union(features)
