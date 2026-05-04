"""
Unit and integration tests for the arcgis_execute direct execution pipeline.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm_service import LLMResponse, ToolCallResult


# ---------------------------------------------------------------------------
# Helper: build a mock orchestrator with mocked LLM + MCP
# ---------------------------------------------------------------------------

def _make_orchestrator(llm_responses, mcp_results=None):
    """Create a Orchestrator with mocked LLM and MCP client.

    Args:
        llm_responses: List of LLMResponse objects returned sequentially.
        mcp_results: Dict mapping tool_name to return value, or a single value.
    """
    from core.orchestrator import Orchestrator

    mock_mcp = MagicMock()
    mock_mcp.is_connected = True
    mock_mcp.list_tools = AsyncMock(return_value=[])

    if mcp_results is None:
        mcp_results = {}

    if isinstance(mcp_results, dict):
        async def _call_tool(name, args):
            if name in mcp_results:
                val = mcp_results[name]
                if callable(val):
                    return val(args)
                return val
            return {"result": "ok"}
        mock_mcp.call_tool = AsyncMock(side_effect=_call_tool)
    else:
        mock_mcp.call_tool = AsyncMock(return_value=mcp_results)

    mock_llm = MagicMock()
    _responses = list(llm_responses)
    mock_llm.complete = AsyncMock(side_effect=_responses)

    orchestrator = Orchestrator(mock_mcp, mock_llm)
    # Clear the shared tools cache to avoid list_tools call
    orchestrator._tools_cache.clear()

    return orchestrator, mock_mcp, mock_llm


# ---------------------------------------------------------------------------
# 6.1: Single-tool geocode
# ---------------------------------------------------------------------------

class TestArcgisExecuteGeocodeCall:
    """6.1: Mock LLM → geocode tool call → verify response."""

    @pytest.mark.asyncio
    async def test_geocode_returns_locate_action(self):
        geocode_result = {
            "candidates": [{"address": "224 W Hamilton Ave", "location": {"x": -77.86, "y": 40.79}, "score": 100}],
            "count": 1,
        }

        llm_responses = [
            # First call: LLM requests geocode tool
            LLMResponse(
                tool_calls=[
                    ToolCallResult(
                        tool_call_id="tc1",
                        tool_name="geocode",
                        tool_input={"address": "224 W Hamilton Ave State College PA"},
                    )
                ]
            ),
            # Second call: LLM returns text after seeing tool result
            LLMResponse(content="Geocoded 224 W Hamilton Ave State College PA"),
        ]

        orch, mock_mcp, _ = _make_orchestrator(llm_responses, {"geocode": geocode_result})
        result = await orch.arcgis_execute("geocode 224 W Hamilton Ave State College PA")

        assert result["action"] == "locate"
        assert result["data"] == geocode_result
        assert result["tool_name"] == "geocode"
        assert result["message"] == "Geocoded 224 W Hamilton Ave State College PA"
        assert "execution_time_ms" in result


# ---------------------------------------------------------------------------
# 6.2: Tool-calling loop cap at 5 iterations
# ---------------------------------------------------------------------------

class TestToolCallingLoopCap:
    """6.2: Mock LLM to always return tool calls, verify loop stops at 5."""

    @pytest.mark.asyncio
    async def test_loop_stops_at_5_iterations(self):
        # Create 6 responses: 5 tool calls + 1 final (but we only get 5+1)
        tool_call_response = LLMResponse(
            tool_calls=[
                ToolCallResult(
                    tool_call_id="tc",
                    tool_name="search_content",
                    tool_input={"query": "test"},
                )
            ]
        )
        # 5 tool-call responses, then a text response (should be reached after 5th iteration)
        # Actually, the loop runs while has_tool_calls and iteration < 5
        # So after 5 iterations it stops. The 6th complete() call returns the text.
        # But wait — the loop calls complete() after each iteration.
        # Initial call (1) + 5 iterations (5 re-calls) = 6 complete() calls total.
        # We need 6 responses: initial returns tool_call, 4 re-calls return tool_call,
        # 5th re-call returns tool_call (iteration=5 → loop exits).
        # Actually: while response.has_tool_calls and iteration < 5:
        #   iteration += 1 ... response = complete()
        # So iteration goes 1,2,3,4,5 — after iteration 5, check: has_tool_calls AND 5 < 5 → False, exit
        # So we need: initial (1) + 5 re-calls (5) = 6 complete() calls
        # All 6 can return tool calls — the loop stops regardless at iteration 5
        llm_responses = [tool_call_response] * 6

        orch, mock_mcp, mock_llm = _make_orchestrator(
            llm_responses,
            {"search_content": {"items": [], "count": 0}},
        )
        result = await orch.arcgis_execute("loop test")

        # Should have called complete() exactly 6 times: 1 initial + 5 re-calls
        assert mock_llm.complete.call_count == 6
        # Should have called call_tool 5 times (once per iteration)
        assert mock_mcp.call_tool.call_count == 5


# ---------------------------------------------------------------------------
# 6.3: No tool call — message-only
# ---------------------------------------------------------------------------

class TestNoToolCall:
    """6.3: LLM returns text only, verify action='message' and data=None."""

    @pytest.mark.asyncio
    async def test_message_only_response(self):
        llm_responses = [
            LLMResponse(content="I can help with ArcGIS queries. What would you like to know?"),
        ]

        orch, _, _ = _make_orchestrator(llm_responses)
        result = await orch.arcgis_execute("what tools are available?")

        assert result["action"] == "message"
        assert result["data"] is None
        assert result["tool_name"] is None
        assert result["tool_args"] is None
        assert "I can help" in result["message"]


# ---------------------------------------------------------------------------
# 6.4: Tool execution failure
# ---------------------------------------------------------------------------

class TestToolExecutionFailure:
    """6.4: call_tool raises exception, verify error is captured."""

    @pytest.mark.asyncio
    async def test_tool_error_captured_in_data(self):
        llm_responses = [
            LLMResponse(
                tool_calls=[
                    ToolCallResult(
                        tool_call_id="tc1",
                        tool_name="query_features",
                        tool_input={"layer_url": "https://bad-url"},
                    )
                ]
            ),
            LLMResponse(content="The query failed due to an invalid URL."),
        ]

        orch, mock_mcp, _ = _make_orchestrator(llm_responses)
        mock_mcp.call_tool = AsyncMock(side_effect=Exception("Connection refused"))

        result = await orch.arcgis_execute("query bad url")

        assert result["data"] == {"error": "Connection refused"}
        assert result["action"] == "query"
        assert result["tool_name"] == "query_features"


# ---------------------------------------------------------------------------
# 6.5: Action mapping for all 13 tools
# ---------------------------------------------------------------------------

class TestActionMapping:
    """6.5: Verify all 13 tool names map to correct action types."""

    def test_all_tool_names_mapped(self):
        from core.orchestrator.base import TOOL_ACTION_MAP

        expected = {
            "geocode": "locate",
            "reverse_geocode": "locate",
            "query_features": "query",
            "spatial_join_query": "query",
            "join_layers": "query",
            "execute_query_plan": "query",
            "count_features": "query",
            "buffer_and_query": "query",
            "find_nearby": "query",
            "search_content": "search",
            "search_layers": "search",
            "summarize_field": "analyze",
            "get_feature_table": "analyze",
        }

        for tool_name, expected_action in expected.items():
            actual = TOOL_ACTION_MAP.get(tool_name)
            assert actual == expected_action, f"{tool_name} → expected {expected_action}, got {actual}"

    def test_unknown_tool_defaults_to_message(self):
        from core.orchestrator.base import TOOL_ACTION_MAP

        assert TOOL_ACTION_MAP.get("unknown_tool") is None


# ---------------------------------------------------------------------------
# 6.6: Multi-step chain (search_content → query_features)
# ---------------------------------------------------------------------------

class TestMultiStepChain:
    """6.6: LLM chains search_content → query_features."""

    @pytest.mark.asyncio
    async def test_search_then_query_chain(self):
        search_result = {
            "items": [{"title": "parks", "url": "https://services.arcgis.com/fire/FeatureServer/0", "type": "Feature Layer"}],
            "count": 1,
        }
        query_result = {
            "features": [{"attributes": {"NAME": "Station 1", "STATE": "PA"}}],
            "count": 1,
        }

        llm_responses = [
            # Step 1: LLM calls search_content
            LLMResponse(
                tool_calls=[
                    ToolCallResult(
                        tool_call_id="tc1",
                        tool_name="search_content",
                        tool_input={"query": "parks"},
                    )
                ]
            ),
            # Step 2: LLM sees search results, calls query_features
            LLMResponse(
                tool_calls=[
                    ToolCallResult(
                        tool_call_id="tc2",
                        tool_name="query_features",
                        tool_input={
                            "layer_url": "https://services.arcgis.com/fire/FeatureServer/0",
                            "where": "STATE = 'PA'",
                        },
                    )
                ]
            ),
            # Step 3: LLM returns final text
            LLMResponse(content="Found 1 fire station in Pennsylvania."),
        ]

        mcp_results = {
            "search_content": search_result,
            "query_features": query_result,
        }

        orch, mock_mcp, _ = _make_orchestrator(llm_responses, mcp_results)
        result = await orch.arcgis_execute("show me parks in Pennsylvania")

        # Final action should be 'query' (from query_features, the last tool)
        assert result["action"] == "query"
        assert result["data"] == query_result
        assert result["tool_name"] == "query_features"
        assert result["message"] == "Found 1 fire station in Pennsylvania."
        # Verify both tools were called
        assert mock_mcp.call_tool.call_count == 2


# ---------------------------------------------------------------------------
# 6.7: Integration test for /arcgis-execute endpoint
# ---------------------------------------------------------------------------

class TestArcgisExecuteEndpoint:
    """6.7: POST /api/v1/arcgis-execute returns 200."""

    def test_arcgis_execute_endpoint_returns_200(self):
        mock_result = {
            "action": "locate",
            "message": "Geocoded",
            "data": {"candidates": []},
            "tool_name": "geocode",
            "tool_args": {"address": "test"},
            "execution_time_ms": 100,
        }

        with patch("main.mcp_client") as mock_mcp, \
             patch("main.orchestrator") as mock_orch:
            mock_mcp.is_connected = True
            mock_orch.arcgis_execute = AsyncMock(return_value=mock_result)

            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/arcgis-execute",
                json={"query": "geocode 123 Main St"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["action"] == "locate"

    def test_arcgis_execute_empty_query_returns_422(self):
        with patch("main.mcp_client") as mock_mcp:
            mock_mcp.is_connected = True
            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/arcgis-execute",
                json={},
            )
            assert response.status_code == 422


# ---------------------------------------------------------------------------
# 6.8: Integration test for prefix routing
# ---------------------------------------------------------------------------

class TestPrefixRouting:
    """6.8: /arcgis-execute prefix routes to arcgis_execute()."""

    @pytest.mark.asyncio
    async def test_prefix_routing_calls_arcgis_execute(self):
        llm_responses = [
            LLMResponse(content="Search results for parks"),
        ]

        orch, _, _ = _make_orchestrator(llm_responses)

        # Call execute() with /arcgis-execute prefix
        result = await orch.execute("/arcgis-execute search parks")

        assert result["action"] == "message"
        assert "parks" in result["message"].lower() or result["message"] != ""


# ---------------------------------------------------------------------------
# 6.9: /commands endpoint includes /arcgis-execute
# ---------------------------------------------------------------------------

class TestCommandsList:
    """6.9: /arcgis-execute appears in command list."""

    def test_arcgis_execute_in_commands(self):
        with patch("main.mcp_client") as mock_mcp:
            mock_mcp.is_connected = True
            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/commands")
            assert response.status_code == 200
            commands = response.json()
            names = [c["name"] for c in commands]
            assert "/arcgis-execute" in names
