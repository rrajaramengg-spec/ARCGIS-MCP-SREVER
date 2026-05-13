"""Unit tests for RAG empty-context guard in query_handler and execute_llm_handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm_service import LLMService
from core.mcp_client import MCPClient
from core.orchestrator.query_handler import QueryHandler


def _make_handler():
    """Create a QueryHandler with mocked MCP and LLM."""
    mock_mcp = MagicMock(spec=MCPClient)
    mock_mcp.is_connected = True
    mock_mcp.call_tool = AsyncMock(return_value={})
    mock_llm = MagicMock(spec=LLMService)
    mock_llm.chat = AsyncMock()
    handler = QueryHandler(
        mcp=mock_mcp, llm=mock_llm, prompts={
            "query_instructions": {
                "system": "You are a test assistant.",
                "human": "{context}\n{query}",
            }
        }, tools_cache=[]
    )
    handler._progress_callback = None
    return handler


class TestRAGEmptyGuardPlanQuery:
    """RAG empty guard on plan_query (planning-only endpoint)."""

    @pytest.mark.asyncio
    async def test_empty_rag_returns_message_action(self):
        """When RAG returns zero layers and empty context, return message without calling LLM."""
        handler = _make_handler()
        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock) as mock_rag:
            mock_rag.return_value = ("", [])  # empty context, no layers
            result = await handler.plan("find supports near me")

        assert result["action"] == "message"
        assert "No relevant layers" in result["message"]
        # LLM should NOT have been called
        handler._llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_rag_layers_only_proceeds(self):
        """When RAG returns layers but no patterns, pipeline proceeds (calls LLM)."""
        handler = _make_handler()
        mock_response = MagicMock()
        mock_response.content = '{"action": "message", "message": "test"}'
        handler._llm.complete = AsyncMock(return_value=mock_response)
        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock) as mock_rag:
            # layers present, patterns produce context string
            mock_rag.return_value = (
                "=== AVAILABLE LAYERS ===\nCOUNTY: https://example.com/0",
                [{"name": "COUNTY", "url": "https://example.com/0"}],
            )
            result = await handler.plan("show county")

        # LLM SHOULD have been called (partial context is OK)
        handler._llm.complete.assert_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_context_with_no_layers_triggers_guard(self):
        """Whitespace-only context string with empty layers triggers guard."""
        handler = _make_handler()
        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock) as mock_rag:
            mock_rag.return_value = ("   \n  \n  ", [])  # whitespace only
            result = await handler.plan("random query")

        assert result["action"] == "message"
        assert "No relevant layers" in result["message"]


class TestRAGEmptyGuardExecute:
    """RAG empty guard on execute (full pipeline endpoint)."""

    @pytest.mark.asyncio
    async def test_empty_rag_returns_message_on_execute(self):
        """execute() returns message action when RAG is empty."""
        handler = _make_handler()
        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock) as mock_rag:
            mock_rag.return_value = ("", [])
            result = await handler.execute("find nearest support")

        assert result["action"] == "message"
        assert "No relevant layers" in result["message"]
        assert "query_id" in result
        handler._llm.chat.assert_not_called()
