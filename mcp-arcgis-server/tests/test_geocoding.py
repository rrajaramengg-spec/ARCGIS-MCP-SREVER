"""
Unit tests for geocoding tools (geocode, reverse_geocode).
"""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


# ── geocode tests ───────────────────────────────────────────────────


class TestGeocode:
    """Tests for geocode standalone function."""

    @pytest.mark.asyncio
    async def test_single_match(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        mock_client.geocode.return_value = [
            {
                "score": 100,
                "address": "1600 Pennsylvania Ave NW, Washington, DC 20500",
                "location": {"x": -77.0365, "y": 38.8977},
                "attributes": {},
                "geometry": {"x": -77.0365, "y": 38.8977},
            }
        ]
        result = await geocode(mock_client, "1600 Pennsylvania Ave NW")
        assert result["count"] == 1
        assert result["candidates"][0]["score"] == 100
        assert result["query"] == "1600 Pennsylvania Ave NW"

    @pytest.mark.asyncio
    async def test_multiple_candidates(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        mock_client.geocode.return_value = [
            {"score": 95, "address": "Main St, Denver, CO"},
            {"score": 80, "address": "Main St, Boulder, CO"},
        ]
        result = await geocode(mock_client, "Main St", max_results=5)
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_no_results(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        mock_client.geocode.return_value = []
        result = await geocode(mock_client, "xyznonexistent12345")
        assert result["count"] == 0
        assert result["candidates"] == []

    @pytest.mark.asyncio
    async def test_empty_address_rejected(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        result = await geocode(mock_client, "")
        assert result["error"] == "Invalid input"

    @pytest.mark.asyncio
    async def test_whitespace_address_rejected(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        result = await geocode(mock_client, "   ")
        assert result["error"] == "Invalid input"

    @pytest.mark.asyncio
    async def test_max_results_capped_at_10(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        mock_client.geocode.return_value = []
        await geocode(mock_client, "test", max_results=50)
        mock_client.geocode.assert_called_once_with(
            address="test", max_results=10, out_sr=4326
        )

    @pytest.mark.asyncio
    async def test_gis_unavailable(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        mock_client.geocode.side_effect = RuntimeError("GIS not authenticated")
        result = await geocode(mock_client, "test address")
        assert result["error"] == "GIS not authenticated"

    @pytest.mark.asyncio
    async def test_general_exception(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import geocode

        mock_client.geocode.side_effect = Exception("service down")
        result = await geocode(mock_client, "test address")
        assert result["error"] == "geocode failed"
        assert "service down" in result["detail"]


# ── reverse_geocode tests ───────────────────────────────────────────


class TestReverseGeocode:
    """Tests for reverse_geocode standalone function."""

    @pytest.mark.asyncio
    async def test_valid_coordinates(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        mock_client.reverse_geocode.return_value = {
            "address": "1600 Pennsylvania Ave NW",
            "location": {"x": -77.0365, "y": 38.8977},
            "score": 100,
            "address_components": {"City": "Washington", "Region": "DC"},
        }
        result = await reverse_geocode(mock_client, 38.8977, -77.0365)
        assert result["address"] == "1600 Pennsylvania Ave NW"

    @pytest.mark.asyncio
    async def test_ocean_coordinates(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        mock_client.reverse_geocode.return_value = {
            "address": None,
            "location": {"x": 0.0, "y": 0.0},
            "score": None,
            "address_components": {},
        }
        result = await reverse_geocode(mock_client, 0.0, 0.0)
        assert result["address"] is None

    @pytest.mark.asyncio
    async def test_invalid_latitude_too_high(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        result = await reverse_geocode(mock_client, 91.0, -77.0)
        assert result["error"] == "Invalid latitude"

    @pytest.mark.asyncio
    async def test_invalid_latitude_too_low(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        result = await reverse_geocode(mock_client, -91.0, -77.0)
        assert result["error"] == "Invalid latitude"

    @pytest.mark.asyncio
    async def test_invalid_longitude_too_high(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        result = await reverse_geocode(mock_client, 39.0, 181.0)
        assert result["error"] == "Invalid longitude"

    @pytest.mark.asyncio
    async def test_invalid_longitude_too_low(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        result = await reverse_geocode(mock_client, 39.0, -181.0)
        assert result["error"] == "Invalid longitude"

    @pytest.mark.asyncio
    async def test_gis_unavailable(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        mock_client.reverse_geocode.side_effect = RuntimeError(
            "GIS not authenticated"
        )
        result = await reverse_geocode(mock_client, 39.0, -105.0)
        assert result["error"] == "GIS not authenticated"

    @pytest.mark.asyncio
    async def test_general_exception(self, mock_client):
        from mcp_arcgis_server.tools.geocoding import reverse_geocode

        mock_client.reverse_geocode.side_effect = Exception("network error")
        result = await reverse_geocode(mock_client, 39.0, -105.0)
        assert result["error"] == "reverse_geocode failed"
