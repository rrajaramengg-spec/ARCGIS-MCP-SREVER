"""
Unit tests for proximity tool (find_nearby).
"""

import json

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.fixture
def mock_ctx():
    ctx = AsyncMock()
    return ctx


SAMPLE_LOCATION = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
SAMPLE_BUFFER = {
    "rings": [[[-105, 39], [-105, 40], [-104, 40], [-104, 39], [-105, 39]]],
    "spatialReference": {"wkid": 4326},
}


def _make_feature(name, x, y):
    return {
        "attributes": {"Name": name},
        "geometry": {"x": x, "y": y, "spatialReference": {"wkid": 4326}},
    }


class TestFindNearby:
    """Tests for find_nearby standalone function."""

    @pytest.mark.asyncio
    async def test_basic_proximity(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        mock_client.query_layer.return_value = {
            "features": [
                _make_feature("Near", -104.91, 39.71),
                _make_feature("Far", -104.95, 39.75),
            ],
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
        }
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=5,
            unit="miles",
        )
        assert result["count"] == 2
        assert result["search_radius"] == 5
        assert "buffer_geometry" in result
        assert "near_features" in result
        assert "proximity_lines" in result
        assert len(result["near_features"]) == 2
        assert len(result["proximity_lines"]) == 2
        # Near features should have no distance property
        assert "distance" not in result["near_features"][0]
        # Proximity lines should have distance in feet in attributes
        assert result["proximity_lines"][0]["attributes"]["distance"] is not None
        assert result["proximity_lines"][0]["attributes"]["distance_unit"] == "feet"
        assert result["proximity_lines"][0]["attributes"]["target_id"] == 0
        # First line should have shorter distance (sorted by distance)
        assert result["proximity_lines"][0]["attributes"]["distance"] <= result["proximity_lines"][1]["attributes"]["distance"]

    @pytest.mark.asyncio
    async def test_distance_in_proximity_lines(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        mock_client.query_layer.return_value = {
            "features": [_make_feature("A", -104.91, 39.71)],
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
        }
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=10,
            unit="miles",
        )
        # Distance should be in proximity lines, not near features
        near_feat = result["near_features"][0]
        assert "distance" not in near_feat
        assert "distance_unit" not in near_feat
        # Proximity line should have distance in feet
        prox_line = result["proximity_lines"][0]
        assert prox_line["attributes"]["distance"] is not None
        assert prox_line["attributes"]["distance_unit"] == "feet"
        assert isinstance(prox_line["attributes"]["distance"], float)

    @pytest.mark.asyncio
    async def test_max_results_cap(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        features = [_make_feature(f"F{i}", -104.9 + i * 0.01, 39.7) for i in range(10)]
        mock_client.query_layer.return_value = {
            "features": features,
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
        }
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=10,
            unit="miles",
            max_results=3,
        )
        assert result["count"] == 3
        assert result["total_in_radius"] == 10
        assert len(result["near_features"]) == 3
        assert len(result["proximity_lines"]) == 3

    @pytest.mark.asyncio
    async def test_no_results(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        mock_client.query_layer.return_value = {
            "features": [],
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
        }
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=1,
            unit="miles",
        )
        assert result["count"] == 0
        assert result["near_features"] == []
        assert result["proximity_lines"] == []
        assert result["buffer_geometry"] == SAMPLE_BUFFER

    @pytest.mark.asyncio
    async def test_where_filter(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        mock_client.query_layer.return_value = {"features": []}
        await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=5,
            unit="miles",
            where="Status='Active'",
        )
        call_kwargs = mock_client.query_layer.call_args.kwargs
        assert call_kwargs["where"] == "Status='Active'"

    @pytest.mark.asyncio
    async def test_invalid_unit(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=5,
            unit="leagues",
        )
        assert result["error"] == "Invalid unit"

    @pytest.mark.asyncio
    async def test_negative_radius(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=-1,
            unit="miles",
        )
        assert result["error"] == "Invalid radius"

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.side_effect = Exception("timeout")
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=5,
            unit="miles",
        )
        assert result["error"] == "find_nearby failed"

    @pytest.mark.asyncio
    async def test_polygon_geometry_input(self, mock_client, mock_ctx):
        """find_nearby accepts polygon geometry, not just points."""
        from mcp_arcgis_server.tools.proximity import find_nearby

        polygon_geom = {
            "rings": [[[-105, 39], [-105, 40], [-104, 40], [-104, 39], [-105, 39]]],
            "spatialReference": {"wkid": 4326},
        }
        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        mock_client.query_layer.return_value = {
            "features": [_make_feature("Near", -104.91, 39.71)],
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
        }
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(polygon_geom),
            radius=5,
            unit="miles",
        )
        assert result["count"] == 1
        # Proximity line should exist with distance in feet
        assert len(result["proximity_lines"]) == 1
        assert result["proximity_lines"][0]["attributes"]["distance"] is not None
        # Verify buffer_geometry was called with normalized polygon
        mock_client.buffer_geometry.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_geometry_json(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            "not valid json",
            radius=5,
            unit="miles",
        )
        assert result["error"] == "Invalid geometry"
