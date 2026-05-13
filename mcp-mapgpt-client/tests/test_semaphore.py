"""Unit tests for MCPClient semaphore throttling and ArcGIS tool classification."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.mcp_client import MCPClient, _ARCGIS_TOOLS


class TestIsArcgisTool:
    """Tests for the _is_arcgis_tool static classifier."""

    def test_known_arcgis_tools(self):
        for tool_name in [
            "query_features",
            "geocode",
            "buffer_and_query",
            "find_nearby",
            "execute_query_plan",
            "union_geometries",
            "count_features",
            "summarize_field",
        ]:
            assert MCPClient._is_arcgis_tool(tool_name) is True, tool_name

    def test_non_arcgis_tools_bypass(self):
        for tool_name in [
            "some_custom_tool",
            "internal_computation",
            "",
        ]:
            assert MCPClient._is_arcgis_tool(tool_name) is False, tool_name


class TestSemaphoreThrottling:
    """Tests for concurrency throttling via asyncio.Semaphore."""

    def test_default_semaphore_value(self):
        client = MCPClient()
        assert client._arcgis_semaphore._value == 10

    def test_custom_semaphore_value(self):
        client = MCPClient(arcgis_max_concurrent=5)
        assert client._arcgis_semaphore._value == 5

    @pytest.mark.asyncio
    async def test_arcgis_tool_acquires_semaphore(self):
        """ArcGIS tools should acquire the semaphore before calling."""
        client = MCPClient(arcgis_max_concurrent=2)
        # Mock session to avoid ConnectionError.
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.isError = False
        mock_result.content = []
        mock_session.call_tool = AsyncMock(return_value=mock_result)
        client._session = mock_session

        # Call two ArcGIS tools concurrently — should both proceed.
        results = await asyncio.gather(
            client.call_tool("query_features", {"layer_url": "u", "where": "1=1"}),
            client.call_tool("geocode", {"address": "test"}),
        )
        assert mock_session.call_tool.await_count == 2

    @pytest.mark.asyncio
    async def test_non_arcgis_tool_bypasses_semaphore(self):
        """Non-ArcGIS tools should not consume semaphore slots."""
        client = MCPClient(arcgis_max_concurrent=1)
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.isError = False
        mock_result.content = []
        mock_session.call_tool = AsyncMock(return_value=mock_result)
        client._session = mock_session

        # Even with semaphore=1, a non-ArcGIS tool should not block.
        await client.call_tool("some_custom_tool", {})
        assert mock_session.call_tool.await_count == 1
        # Semaphore should still be at full capacity.
        assert client._arcgis_semaphore._value == 1

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_arcgis_calls(self):
        """When semaphore is 1, concurrent ArcGIS calls should serialize."""
        client = MCPClient(arcgis_max_concurrent=1)

        call_order: list[str] = []
        semaphore_was_zero = False

        original_call_tool = AsyncMock()

        async def slow_call_tool(name, **kwargs):
            nonlocal semaphore_was_zero
            call_order.append(f"start:{name}")
            # Check if semaphore is fully consumed.
            if client._arcgis_semaphore._value == 0:
                semaphore_was_zero = True
            await asyncio.sleep(0.05)
            call_order.append(f"end:{name}")
            result = MagicMock()
            result.isError = False
            result.content = []
            return result

        mock_session = MagicMock()
        mock_session.call_tool = slow_call_tool
        client._session = mock_session

        await asyncio.gather(
            client.call_tool("query_features", {"layer_url": "u"}),
            client.call_tool("geocode", {"address": "test"}),
        )

        # With semaphore=1, the second call must wait for the first to finish.
        # So the order should be: start:first, end:first, start:second, end:second.
        assert call_order[0].startswith("start:")
        assert call_order[1].startswith("end:")
        assert len(call_order) == 4
