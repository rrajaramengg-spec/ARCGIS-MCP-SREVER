"""
Unit tests for discovery tools (search_content, search_layers).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


# ── search_content tests ────────────────────────────────────────────


class TestSearchContent:
    """Tests for search_content standalone function."""

    @pytest.mark.asyncio
    async def test_keyword_search(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_content

        mock_client.search_content.return_value = [
            {"title": "Parcels", "type": "Feature Layer", "url": "https://example.com/0"},
            {"title": "Zoning", "type": "Feature Layer", "url": "https://example.com/1"},
        ]
        result = await search_content(mock_client, "parcels")
        assert result["count"] == 2
        assert result["query"] == "parcels"
        assert len(result["items"]) == 2
        mock_client.search_content.assert_called_once_with(
            query="parcels", item_type=None, max_items=10
        )

    @pytest.mark.asyncio
    async def test_type_filter(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_content

        mock_client.search_content.return_value = [
            {"title": "Base Map", "type": "Map Service"},
        ]
        result = await search_content(mock_client, "base", item_type="Map Service")
        assert result["count"] == 1
        mock_client.search_content.assert_called_once_with(
            query="base", item_type="Map Service", max_items=10
        )

    @pytest.mark.asyncio
    async def test_max_cap_at_50(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_content

        mock_client.search_content.return_value = []
        result = await search_content(mock_client, "data", max_items=100)
        assert result.get("capped") is True
        mock_client.search_content.assert_called_once_with(
            query="data", item_type=None, max_items=50
        )

    @pytest.mark.asyncio
    async def test_no_auth_error(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_content

        mock_client.search_content.side_effect = RuntimeError("GIS not authenticated")
        result = await search_content(mock_client, "test")
        assert result["error"] == "GIS not authenticated"

    @pytest.mark.asyncio
    async def test_empty_query_rejected(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_content

        result = await search_content(mock_client, "")
        assert result["error"] == "Invalid input"

    @pytest.mark.asyncio
    async def test_whitespace_query_rejected(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_content

        result = await search_content(mock_client, "   ")
        assert result["error"] == "Invalid input"

    @pytest.mark.asyncio
    async def test_general_exception(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_content

        mock_client.search_content.side_effect = Exception("network timeout")
        result = await search_content(mock_client, "test")
        assert result["error"] == "search_content failed"
        assert "network timeout" in result["detail"]


# ── search_layers tests ─────────────────────────────────────────────


class TestSearchLayers:
    """Tests for search_layers standalone function."""

    @pytest.mark.asyncio
    async def test_service_url_response(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_layers

        mock_client.get_service_layers.return_value = [
            {"id": 0, "name": "Parcels", "type": "Feature Layer"},
            {"id": 1, "name": "Zoning", "type": "Feature Layer"},
        ]
        result = await search_layers(
            mock_client, service_url="https://example.com/MapServer"
        )
        assert result["count"] == 2
        assert result["source"] == "service_url"
        mock_client.get_service_layers.assert_called_once_with(
            "https://example.com/MapServer"
        )

    @pytest.mark.asyncio
    async def test_keyword_search(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_layers

        mock_client.search_content.return_value = [
            {"title": "Water Lines", "type": "Feature Layer"},
        ]
        result = await search_layers(mock_client, query="water")
        assert result["count"] == 1
        assert result["source"] == "portal_search"
        mock_client.search_content.assert_called_once_with(
            query="water", item_type="Feature Layer", max_items=50
        )

    @pytest.mark.asyncio
    async def test_missing_params_rejected(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_layers

        result = await search_layers(mock_client)
        assert result["error"] == "Invalid input"
        assert "at least one" in result["detail"].lower()

    @pytest.mark.asyncio
    async def test_no_auth_error(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_layers

        mock_client.get_service_layers.side_effect = RuntimeError("GIS not authenticated")
        result = await search_layers(
            mock_client, service_url="https://example.com/MapServer"
        )
        assert result["error"] == "GIS not authenticated"

    @pytest.mark.asyncio
    async def test_general_exception(self, mock_client):
        from mcp_arcgis_server.tools.discovery import search_layers

        mock_client.get_service_layers.side_effect = Exception("connection refused")
        result = await search_layers(
            mock_client, service_url="https://example.com/MapServer"
        )
        assert result["error"] == "search_layers failed"
