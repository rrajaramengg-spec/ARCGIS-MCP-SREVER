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
            ]
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
        # Should be sorted by distance (nearest first)
        assert result["features"][0]["distance"] <= result["features"][1]["distance"]

    @pytest.mark.asyncio
    async def test_distance_enrichment(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        mock_client.query_layer.return_value = {
            "features": [_make_feature("A", -104.91, 39.71)]
        }
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=10,
            unit="miles",
        )
        feat = result["features"][0]
        assert feat["distance"] is not None
        assert feat["distance_unit"] == "miles"
        assert isinstance(feat["distance"], float)

    @pytest.mark.asyncio
    async def test_max_results_cap(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        features = [_make_feature(f"F{i}", -104.9 + i * 0.01, 39.7) for i in range(10)]
        mock_client.query_layer.return_value = {"features": features}
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

    @pytest.mark.asyncio
    async def test_no_results(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.proximity import find_nearby

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER
        mock_client.query_layer.return_value = {"features": []}
        result = await find_nearby(
            mock_client,
            mock_ctx,
            "https://example.com/0",
            json.dumps(SAMPLE_LOCATION),
            radius=1,
            unit="miles",
        )
        assert result["count"] == 0
        assert result["features"] == []

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
            "features": [_make_feature("Near", -104.91, 39.71)]
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
        assert result["features"][0]["distance"] is not None
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
        assert result["error"] == "Invalid geometry JSON"
