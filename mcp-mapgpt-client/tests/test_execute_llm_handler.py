"""
Unit tests for the execute_llm RAG-augmented LLM tool-calling pipeline.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm_service import LLMResponse, ToolCallResult


def _make_orchestrator(llm_responses, mcp_results=None):
    """Create a MapGPTOrchestrator with mocked LLM and MCP client."""
    from core.orchestrator import MapGPTOrchestrator

    mock_mcp = MagicMock()
    mock_mcp.is_connected = True
    mock_mcp.list_tools = AsyncMock(return_value=[])

    if mcp_results is None:
        mcp_results = {}

    if isinstance(mcp_results, dict):
        async def _call_tool(name, args, **kwargs):
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

    orchestrator = MapGPTOrchestrator(mock_mcp, mock_llm)
    orchestrator._tools_cache.clear()

    return orchestrator, mock_mcp, mock_llm


# Mock RAG context for all tests
_MOCK_RAG_CONTEXT = (
    "=== AVAILABLE LAYERS ===\nLayer: COUNTY\nURL: https://example.com/0\n",
    [{"layer_name": "COUNTY", "url": "https://example.com/0", "purpose": "County boundaries", "fields": []}],
)


class TestExecuteLLMSuccessfulExecution:
    """Successful tool-calling execution with RAG context."""

    @pytest.mark.asyncio
    @patch("core.orchestrator.execute_llm_handler.build_rag_context", new_callable=AsyncMock)
    @patch("core.orchestrator.execute_llm_handler.ResponseCache")
    @patch("core.orchestrator.execute_llm_handler.ConversationHistory")
    async def test_tool_calling_returns_execute_response(
        self, mock_history, mock_cache, mock_rag
    ):
        mock_rag.return_value = _MOCK_RAG_CONTEXT
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.store_query_mapping = AsyncMock(return_value=True)

        query_result = {"features": [{"attributes": {"NAME": "Madison"}}], "count": 1}
        llm_responses = [
            LLMResponse(
                tool_calls=[
                    ToolCallResult(
                        tool_call_id="tc1",
                        tool_name="query_features",
                        tool_input={"layer_url": "https://example.com/0", "where": "UPPER(NAME) LIKE '%MADISON%'"},
                    )
                ]
            ),
            LLMResponse(content="Found 1 feature in Madison County."),
        ]

        orch, _, _ = _make_orchestrator(llm_responses, {"query_features": query_result})
        result = await orch.execute_llm("show counties named madison")

        assert result["action"] == "query"
        assert result["data"] == query_result
        assert result["tool_name"] == "query_features"
        assert "query_id" in result
        assert "execution_time_ms" in result
        assert result["timing"]["rag_ms"] >= 0


class TestExecuteLLMCacheHit:
    """Cache hit returns immediately with 5-min TTL verification."""

    @pytest.mark.asyncio
    @patch("core.orchestrator.execute_llm_handler.build_rag_context", new_callable=AsyncMock)
    @patch("core.orchestrator.execute_llm_handler.ResponseCache")
    async def test_cache_hit_skips_llm(self, mock_cache, mock_rag):
        mock_rag.return_value = _MOCK_RAG_CONTEXT
        cached = {"action": "query", "message": "cached result", "data": {"features": []}}
        mock_cache.get = AsyncMock(return_value=cached)
        mock_cache.store_query_mapping = AsyncMock(return_value=True)

        llm_responses = [LLMResponse(content="should not be called")]
        orch, _, mock_llm = _make_orchestrator(llm_responses)
        result = await orch.execute_llm("cached query")

        assert result["action"] == "query"
        assert result["message"] == "cached result"
        assert "query_id" in result
        # LLM should NOT have been called
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    @patch("core.orchestrator.execute_llm_handler.build_rag_context", new_callable=AsyncMock)
    @patch("core.orchestrator.execute_llm_handler.ResponseCache")
    @patch("core.orchestrator.execute_llm_handler.ConversationHistory")
    async def test_cache_set_uses_5min_ttl(self, mock_history, mock_cache, mock_rag):
        mock_rag.return_value = _MOCK_RAG_CONTEXT
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.store_query_mapping = AsyncMock(return_value=True)

        llm_responses = [LLMResponse(content="No tools needed.")]
        orch, _, _ = _make_orchestrator(llm_responses)
        await orch.execute_llm("simple question")

        # Verify TTL=300 (5 minutes) was passed
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args.kwargs.get("ttl") == 300 or (
            len(call_args.args) >= 4 and call_args.args[3] == 300
        )


class TestExecuteLLMNoToolsCalled:
    """LLM responds with text only — message action."""

    @pytest.mark.asyncio
    @patch("core.orchestrator.execute_llm_handler.build_rag_context", new_callable=AsyncMock)
    @patch("core.orchestrator.execute_llm_handler.ResponseCache")
    @patch("core.orchestrator.execute_llm_handler.ConversationHistory")
    async def test_message_action_when_no_tools(
        self, mock_history, mock_cache, mock_rag
    ):
        mock_rag.return_value = _MOCK_RAG_CONTEXT
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.store_query_mapping = AsyncMock(return_value=True)

        llm_responses = [
            LLMResponse(content="I can help with geospatial queries."),
        ]

        orch, _, _ = _make_orchestrator(llm_responses)
        result = await orch.execute_llm("what can you do?")

        assert result["action"] == "message"
        assert result["data"] is None
        assert result["tool_name"] is None
        assert "I can help" in result["message"]


class TestExecuteLLMToolError:
    """Tool execution error is handled gracefully."""

    @pytest.mark.asyncio
    @patch("core.orchestrator.execute_llm_handler.build_rag_context", new_callable=AsyncMock)
    @patch("core.orchestrator.execute_llm_handler.ResponseCache")
    @patch("core.orchestrator.execute_llm_handler.ConversationHistory")
    async def test_tool_error_captured(
        self, mock_history, mock_cache, mock_rag
    ):
        mock_rag.return_value = _MOCK_RAG_CONTEXT
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.store_query_mapping = AsyncMock(return_value=True)

        llm_responses = [
            LLMResponse(
                tool_calls=[
                    ToolCallResult(
                        tool_call_id="tc1",
                        tool_name="query_features",
                        tool_input={"layer_url": "https://bad"},
                    )
                ]
            ),
            LLMResponse(content="The query failed."),
        ]

        orch, mock_mcp, _ = _make_orchestrator(llm_responses)
        mock_mcp.call_tool = AsyncMock(side_effect=Exception("Connection refused"))

        result = await orch.execute_llm("query bad layer")

        assert result["data"] == {"error": "Connection refused"}
        assert result["tool_name"] == "query_features"


class TestExecuteLLMRAGContextInjected:
    """RAG context is injected into the system prompt."""

    @pytest.mark.asyncio
    @patch("core.orchestrator.execute_llm_handler.build_rag_context", new_callable=AsyncMock)
    @patch("core.orchestrator.execute_llm_handler.ResponseCache")
    @patch("core.orchestrator.execute_llm_handler.ConversationHistory")
    async def test_rag_context_in_user_message(
        self, mock_history, mock_cache, mock_rag
    ):
        mock_rag.return_value = _MOCK_RAG_CONTEXT
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.store_query_mapping = AsyncMock(return_value=True)

        llm_responses = [LLMResponse(content="Done.")]
        orch, _, mock_llm = _make_orchestrator(llm_responses)
        await orch.execute_llm("test query")

        # Verify the user message contains RAG context
        call_args = mock_llm.complete.call_args
        messages = call_args.args[0] if call_args.args else call_args.kwargs["messages"]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert "AVAILABLE LAYERS" in user_msg["content"]
        assert "COUNTY" in user_msg["content"]


class TestExecuteLLMHistorySummary:
    """Session history stores compact summary, not a full plan."""

    @pytest.mark.asyncio
    @patch("core.orchestrator.execute_llm_handler.build_rag_context", new_callable=AsyncMock)
    @patch("core.orchestrator.execute_llm_handler.ResponseCache")
    @patch("core.orchestrator.execute_llm_handler.ConversationHistory")
    async def test_history_stores_compact_summary(
        self, mock_history, mock_cache, mock_rag
    ):
        mock_rag.return_value = _MOCK_RAG_CONTEXT
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.store_query_mapping = AsyncMock(return_value=True)
        mock_history.get_turns = AsyncMock(return_value=[])
        mock_history.add_message = AsyncMock(return_value=True)

        llm_responses = [
            LLMResponse(
                tool_calls=[
                    ToolCallResult(
                        tool_call_id="tc1",
                        tool_name="geocode",
                        tool_input={"address": "123 Main St"},
                    )
                ]
            ),
            LLMResponse(content="Geocoded successfully."),
        ]

        orch, _, _ = _make_orchestrator(llm_responses, {"geocode": {"candidates": []}})
        await orch.execute_llm("locate 123 Main St", session_id="sess-1")

        # History should store individual messages via add_message (not add_turn)
        assert mock_history.add_message.call_count >= 1
        # Verify at least one call has session_id as first arg
        first_call = mock_history.add_message.call_args_list[0]
        assert first_call.args[0] == "sess-1"
