"""
Unit tests for geometry utility functions.
Tests: normalize_geometry, get_centroid, compute_distance, UNIT_TO_METERS.
"""

import math
import pytest


class TestNormalizeGeometry:
    """Tests for normalize_geometry — GeoJSON to ArcGIS JSON conversion."""

    def test_point_geojson(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        result = normalize_geometry(
            {"type": "Point", "coordinates": [-104.9, 39.7]}
        )
        assert result["x"] == -104.9
        assert result["y"] == 39.7
        assert result["spatialReference"]["wkid"] == 4326

    def test_polygon_geojson(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        coords = [[[-105, 39], [-105, 40], [-104, 40], [-104, 39], [-105, 39]]]
        result = normalize_geometry(
            {"type": "Polygon", "coordinates": coords}
        )
        assert result["rings"] == coords
        assert result["spatialReference"]["wkid"] == 4326

    def test_linestring_geojson(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        coords = [[-105, 39], [-104, 40]]
        result = normalize_geometry(
            {"type": "LineString", "coordinates": coords}
        )
        assert result["paths"] == [coords]

    def test_multipoint_geojson(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        coords = [[-105, 39], [-104, 40]]
        result = normalize_geometry(
            {"type": "MultiPoint", "coordinates": coords}
        )
        assert result["points"] == coords

    def test_multilinestring_geojson(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        coords = [[[-105, 39], [-104, 40]], [[-103, 38], [-102, 37]]]
        result = normalize_geometry(
            {"type": "MultiLineString", "coordinates": coords}
        )
        assert result["paths"] == coords

    def test_multipolygon_geojson(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        ring1 = [[-105, 39], [-105, 40], [-104, 40], [-104, 39], [-105, 39]]
        ring2 = [[-103, 38], [-103, 39], [-102, 39], [-102, 38], [-103, 38]]
        result = normalize_geometry(
            {"type": "MultiPolygon", "coordinates": [[ring1], [ring2]]}
        )
        assert ring1 in result["rings"]
        assert ring2 in result["rings"]

    def test_arcgis_json_passthrough(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        arcgis_geom = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        result = normalize_geometry(arcgis_geom)
        assert result is arcgis_geom  # same dict, not converted

    def test_arcgis_polygon_passthrough(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        arcgis_geom = {
            "rings": [[[-105, 39], [-105, 40], [-104, 40], [-104, 39], [-105, 39]]],
            "spatialReference": {"wkid": 4326},
        }
        result = normalize_geometry(arcgis_geom)
        assert result is arcgis_geom

    def test_unknown_geojson_type_passthrough(self):
        from mcp_arcgis_server.arcgis.geometry import normalize_geometry

        geom = {"type": "GeometryCollection", "coordinates": []}
        result = normalize_geometry(geom)
        assert result is geom


class TestGetCentroid:
    """Tests for get_centroid — point extraction from geometries."""

    def test_point_returns_self(self):
        from mcp_arcgis_server.arcgis.geometry import get_centroid

        pt = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        result = get_centroid(pt)
        assert result["x"] == -104.9
        assert result["y"] == 39.7

    def test_polygon_centroid(self):
        from mcp_arcgis_server.arcgis.geometry import get_centroid

        geom = {
            "rings": [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]],
            "spatialReference": {"wkid": 4326},
        }
        result = get_centroid(geom)
        assert abs(result["x"] - 4.0) < 1.0  # rough centroid
        assert abs(result["y"] - 4.0) < 1.0

    def test_polyline_centroid(self):
        from mcp_arcgis_server.arcgis.geometry import get_centroid

        geom = {
            "paths": [[[0, 0], [10, 10]]],
            "spatialReference": {"wkid": 4326},
        }
        result = get_centroid(geom)
        assert result["x"] == 5.0
        assert result["y"] == 5.0

    def test_preserves_spatial_reference(self):
        from mcp_arcgis_server.arcgis.geometry import get_centroid

        geom = {"x": 1, "y": 2, "spatialReference": {"wkid": 3857}}
        result = get_centroid(geom)
        assert result["spatialReference"]["wkid"] == 3857


class TestComputeDistance:
    """Tests for compute_distance — geodesic haversine distance."""

    def test_same_point_zero_distance(self):
        from mcp_arcgis_server.arcgis.geometry import compute_distance

        pt = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        d = compute_distance(pt, pt, unit="meters")
        assert d == 0.0

    def test_known_distance_meters(self):
        from mcp_arcgis_server.arcgis.geometry import compute_distance

        # Denver to Colorado Springs ~ 100 km
        denver = {"x": -104.99, "y": 39.74, "spatialReference": {"wkid": 4326}}
        cos = {"x": -104.82, "y": 38.83, "spatialReference": {"wkid": 4326}}
        d = compute_distance(denver, cos, unit="kilometers")
        assert 90 < d < 120  # rough check

    def test_unit_conversion_miles(self):
        from mcp_arcgis_server.arcgis.geometry import compute_distance

        pt_a = {"x": 0, "y": 0, "spatialReference": {"wkid": 4326}}
        pt_b = {"x": 1, "y": 0, "spatialReference": {"wkid": 4326}}
        d_m = compute_distance(pt_a, pt_b, unit="meters")
        d_mi = compute_distance(pt_a, pt_b, unit="miles")
        assert abs(d_m / 1609.344 - d_mi) < 0.01

    def test_unit_conversion_feet(self):
        from mcp_arcgis_server.arcgis.geometry import compute_distance

        pt_a = {"x": 0, "y": 0, "spatialReference": {"wkid": 4326}}
        pt_b = {"x": 0.01, "y": 0, "spatialReference": {"wkid": 4326}}
        d_m = compute_distance(pt_a, pt_b, unit="meters")
        d_ft = compute_distance(pt_a, pt_b, unit="feet")
        assert abs(d_m / 0.3048 - d_ft) < 0.1


class TestUnitToMeters:
    """Tests for UNIT_TO_METERS constant."""

    def test_all_units_present(self):
        from mcp_arcgis_server.arcgis.geometry import UNIT_TO_METERS

        assert "feet" in UNIT_TO_METERS
        assert "meters" in UNIT_TO_METERS
        assert "kilometers" in UNIT_TO_METERS
        assert "miles" in UNIT_TO_METERS

    def test_meters_is_identity(self):
        from mcp_arcgis_server.arcgis.geometry import UNIT_TO_METERS

        assert UNIT_TO_METERS["meters"] == 1.0


class TestGeodesicBufferFallback:
    """Tests for geodesic_buffer_fallback — math-based buffer polygon generation."""

    def test_point_input_ring_closure(self):
        from mcp_arcgis_server.arcgis.geometry import geodesic_buffer_fallback

        pt = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        result = geodesic_buffer_fallback(pt, radius_meters=1000)
        ring = result["rings"][0]
        # Ring should be closed (first == last)
        assert ring[0] == ring[-1]

    def test_point_input_vertex_count(self):
        from mcp_arcgis_server.arcgis.geometry import geodesic_buffer_fallback

        pt = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        result = geodesic_buffer_fallback(pt, radius_meters=1000, num_points=64)
        ring = result["rings"][0]
        # 64 vertices + 1 closing vertex
        assert len(ring) == 65

    def test_point_input_custom_vertex_count(self):
        from mcp_arcgis_server.arcgis.geometry import geodesic_buffer_fallback

        pt = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        result = geodesic_buffer_fallback(pt, radius_meters=500, num_points=32)
        ring = result["rings"][0]
        assert len(ring) == 33

    def test_spatial_reference_wkid_4326(self):
        from mcp_arcgis_server.arcgis.geometry import geodesic_buffer_fallback

        pt = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        result = geodesic_buffer_fallback(pt, radius_meters=1000)
        assert result["spatialReference"]["wkid"] == 4326

    def test_polygon_input_uses_centroid(self):
        from mcp_arcgis_server.arcgis.geometry import geodesic_buffer_fallback

        poly = {
            "rings": [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]],
            "spatialReference": {"wkid": 4326},
        }
        result = geodesic_buffer_fallback(poly, radius_meters=1000)
        ring = result["rings"][0]
        # All vertices should be roughly centered around polygon centroid
        xs = [p[0] for p in ring[:-1]]
        ys = [p[1] for p in ring[:-1]]
        avg_x = sum(xs) / len(xs)
        avg_y = sum(ys) / len(ys)
        assert abs(avg_x - 4.0) < 1.0
        assert abs(avg_y - 4.0) < 1.0

    def test_buffer_radius_approximate_size(self):
        from mcp_arcgis_server.arcgis.geometry import geodesic_buffer_fallback, compute_distance

        pt = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
        radius_m = 2000
        result = geodesic_buffer_fallback(pt, radius_meters=radius_m)
        ring = result["rings"][0]
        # Check that vertices are approximately `radius_m` from center
        for vertex in ring[:4]:
            vertex_pt = {"x": vertex[0], "y": vertex[1], "spatialReference": {"wkid": 4326}}
            d = compute_distance(pt, vertex_pt, unit="meters")
            # Allow 5% tolerance
            assert abs(d - radius_m) / radius_m < 0.05

    def test_returns_single_ring(self):
        from mcp_arcgis_server.arcgis.geometry import geodesic_buffer_fallback

        pt = {"x": 0, "y": 0, "spatialReference": {"wkid": 4326}}
        result = geodesic_buffer_fallback(pt, radius_meters=500)
        assert len(result["rings"]) == 1
