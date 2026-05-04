"""
Unit tests for analysis tools (summarize_field, get_feature_table).
"""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


# ── summarize_field tests ────────────────────────────────────────────


class TestSummarizeField:
    """Tests for summarize_field standalone function."""

    @pytest.mark.asyncio
    async def test_numeric_field_stats(self, mock_client):
        from mcp_arcgis_server.tools.analysis import summarize_field

        mock_client.get_layer_info.return_value = {
            "fields": [{"name": "Population", "type": "esriFieldTypeDouble"}]
        }
        mock_client.get_field_statistics.side_effect = [
            {
                "count_Population": 100,
                "min_Population": 10,
                "max_Population": 50000,
                "avg_Population": 5000,
                "stddev_Population": 1200,
            },
            {"count_Population": 3},  # null count query
        ]
        result = await summarize_field(
            mock_client, "https://example.com/0", "Population"
        )
        assert result["field"] == "Population"
        assert result["type"] == "esriFieldTypeDouble"
        assert result["statistics"]["count"] == 100
        assert result["statistics"]["min"] == 10
        assert result["null_count"] == 3

    @pytest.mark.asyncio
    async def test_string_field_unique_values(self, mock_client):
        from mcp_arcgis_server.tools.analysis import summarize_field

        mock_client.get_layer_info.return_value = {
            "fields": [{"name": "ZoneType", "type": "esriFieldTypeString"}]
        }
        mock_client.get_unique_values.return_value = [
            {"value": "Residential", "count": 50},
            {"value": "Commercial", "count": 30},
            {"value": "Industrial", "count": 20},
        ]
        result = await summarize_field(
            mock_client, "https://example.com/0", "ZoneType"
        )
        assert result["field"] == "ZoneType"
        assert result["distinct_count"] == 3
        assert result["unique_values"][0]["value"] == "Residential"

    @pytest.mark.asyncio
    async def test_invalid_field_name(self, mock_client):
        from mcp_arcgis_server.tools.analysis import summarize_field

        mock_client.get_layer_info.return_value = {
            "fields": [{"name": "Name", "type": "esriFieldTypeString"}]
        }
        result = await summarize_field(
            mock_client, "https://example.com/0", "NonExistent"
        )
        assert result["error"] == "Invalid field"

    @pytest.mark.asyncio
    async def test_case_insensitive_field_match(self, mock_client):
        from mcp_arcgis_server.tools.analysis import summarize_field

        mock_client.get_layer_info.return_value = {
            "fields": [{"name": "POPULATION", "type": "esriFieldTypeInteger"}]
        }
        mock_client.get_field_statistics.return_value = {"count_POPULATION": 50}
        result = await summarize_field(
            mock_client, "https://example.com/0", "population"
        )
        assert result["field"] == "POPULATION"

    @pytest.mark.asyncio
    async def test_custom_statistics(self, mock_client):
        from mcp_arcgis_server.tools.analysis import summarize_field

        mock_client.get_layer_info.return_value = {
            "fields": [{"name": "Value", "type": "esriFieldTypeDouble"}]
        }
        mock_client.get_field_statistics.side_effect = [
            {"min_Value": 1, "max_Value": 100},
            {"count_Value": 0},
        ]
        result = await summarize_field(
            mock_client,
            "https://example.com/0",
            "Value",
            statistics="min,max",
        )
        assert result["statistics"]["min"] == 1
        assert result["statistics"]["max"] == 100

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_client):
        from mcp_arcgis_server.tools.analysis import summarize_field

        mock_client.get_layer_info.side_effect = Exception("timeout")
        result = await summarize_field(
            mock_client, "https://example.com/0", "Field1"
        )
        assert result["error"] == "summarize_field failed"


# ── get_feature_table tests ─────────────────────────────────────────


class TestGetFeatureTable:
    """Tests for get_feature_table standalone function."""

    @pytest.mark.asyncio
    async def test_json_format(self, mock_client):
        from mcp_arcgis_server.tools.analysis import get_feature_table

        mock_client.query_layer.side_effect = [
            {
                "features": [
                    {"attributes": {"Name": "A", "Value": 1}},
                    {"attributes": {"Name": "B", "Value": 2}},
                ]
            },
            {"count": 2},
        ]
        result = await get_feature_table(mock_client, "https://example.com/0")
        assert result["columns"] == ["Name", "Value"]
        assert result["rows"] == [["A", 1], ["B", 2]]
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_markdown_format(self, mock_client):
        from mcp_arcgis_server.tools.analysis import get_feature_table

        mock_client.query_layer.side_effect = [
            {
                "features": [
                    {"attributes": {"Name": "A", "Value": 1}},
                ]
            },
            {"count": 1},
        ]
        result = await get_feature_table(
            mock_client, "https://example.com/0", format="markdown"
        )
        assert "table" in result
        assert "| Name | Value |" in result["table"]
        assert "| A | 1 |" in result["table"]

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        from mcp_arcgis_server.tools.analysis import get_feature_table

        mock_client.query_layer.return_value = {"features": []}
        mock_client.get_layer_info.return_value = {
            "fields": [
                {"name": "Name"},
                {"name": "Value"},
            ]
        }
        result = await get_feature_table(mock_client, "https://example.com/0")
        assert result["count"] == 0
        assert result["rows"] == []

    @pytest.mark.asyncio
    async def test_max_records_cap(self, mock_client):
        from mcp_arcgis_server.tools.analysis import get_feature_table

        mock_client.query_layer.side_effect = [
            {"features": [{"attributes": {"x": 1}}]},
            {"count": 1},
        ]
        result = await get_feature_table(
            mock_client, "https://example.com/0", max_records=9999
        )
        assert result.get("truncated") is True

    @pytest.mark.asyncio
    async def test_field_selection(self, mock_client):
        from mcp_arcgis_server.tools.analysis import get_feature_table

        mock_client.query_layer.side_effect = [
            {"features": [{"attributes": {"Name": "A"}}]},
            {"count": 10},
        ]
        result = await get_feature_table(
            mock_client, "https://example.com/0", fields="Name"
        )
        assert result["count"] == 1
        assert result["total_count"] == 10

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_client):
        from mcp_arcgis_server.tools.analysis import get_feature_table

        mock_client.query_layer.side_effect = Exception("connection error")
        result = await get_feature_table(mock_client, "https://example.com/0")
        assert result["error"] == "get_feature_table failed"
