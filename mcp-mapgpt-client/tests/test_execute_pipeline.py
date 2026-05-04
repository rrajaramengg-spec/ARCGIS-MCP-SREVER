"""Tests for execute pipeline integration with cache and history."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_llm_response(plan_dict):
    resp = MagicMock()
    resp.content = json.dumps(plan_dict)
    resp.tool_calls = []
    resp.has_tool_calls = False
    return resp


PLAN = {"action": "query", "query": [{"type": "where", "layer": "STATIONS", "layer_url": "http://x", "where": "1=1"}], "message": "ok"}
TOOL_RESULT = {"features": [{"attributes": {"NAME": "A"}}], "count": 1}


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=_make_llm_response(PLAN))
    return llm


@pytest.fixture
def mock_mcp():
    mcp = AsyncMock()
    mcp.list_tools = AsyncMock(return_value=[])
    mcp.call_tool = AsyncMock(return_value=TOOL_RESULT)
    return mcp


@pytest.fixture
def prompts():
    return {
        "query_instructions": {
            "system": "You are a spatial query assistant.",
            "human": "Context: {context}\nQuery: {query}",
        }
    }


@pytest.mark.asyncio
async def test_cache_miss_full_pipeline(mock_mcp, mock_llm, prompts):
    """Cache miss → full pipeline runs, response includes query_id."""
    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ResponseCache") as MockCache:
            MockCache.get = AsyncMock(return_value=None)
            MockCache.set = AsyncMock(return_value=True)
            MockCache.store_query_mapping = AsyncMock(return_value=True)
            with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
                MockHistory.get_turns = AsyncMock(return_value=[])
                MockHistory.add_turn = AsyncMock(return_value=True)

                from core.orchestrator.query_handler import QueryHandler

                handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
                result = await handler.execute("show STATIONS", session_id="s1")

    assert "query_id" in result
    assert result["action"] == "query"
    MockCache.set.assert_called_once()
    MockHistory.add_turn.assert_called_once()


@pytest.mark.asyncio
async def test_cache_hit_skips_pipeline(mock_mcp, mock_llm, prompts):
    """Cache hit → returns cached response without LLM call."""
    cached = {"action": "query", "message": "cached", "data": {}, "execution_time_ms": 100}

    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ResponseCache") as MockCache:
            MockCache.get = AsyncMock(return_value=cached)
            MockCache.store_query_mapping = AsyncMock(return_value=True)

            from core.orchestrator.query_handler import QueryHandler

            handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
            result = await handler.execute("show STATIONS", session_id="s1")

    assert result["message"] == "cached"
    assert "query_id" in result
    mock_llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_query_id_in_response(mock_mcp, mock_llm, prompts):
    """Every execute response includes a query_id UUID."""
    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ResponseCache") as MockCache:
            MockCache.get = AsyncMock(return_value=None)
            MockCache.set = AsyncMock(return_value=True)
            MockCache.store_query_mapping = AsyncMock(return_value=True)
            with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
                MockHistory.get_turns = AsyncMock(return_value=[])
                MockHistory.add_turn = AsyncMock(return_value=True)

                from core.orchestrator.query_handler import QueryHandler

                handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
                result = await handler.execute("show STATIONS", session_id="s1")

    qid = result.get("query_id")
    assert qid is not None
    assert len(qid) == 36  # UUID format


@pytest.mark.asyncio
async def test_history_stores_plan_json(mock_mcp, mock_llm, prompts):
    """After execution, add_turn is called with plan JSON (not message)."""
    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ResponseCache") as MockCache:
            MockCache.get = AsyncMock(return_value=None)
            MockCache.set = AsyncMock(return_value=True)
            MockCache.store_query_mapping = AsyncMock(return_value=True)
            with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
                MockHistory.get_turns = AsyncMock(return_value=[])
                MockHistory.add_turn = AsyncMock(return_value=True)

                from core.orchestrator.query_handler import QueryHandler

                handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
                await handler.execute("show STATIONS", session_id="s1")

    call_args = MockHistory.add_turn.call_args[0]
    assert call_args[0] == "s1"  # session_id
    assert call_args[1] == "show STATIONS"  # query
    assert call_args[2]["action"] == "query"  # plan JSON dict


@pytest.mark.asyncio
async def test_no_history_without_session_id(mock_mcp, mock_llm, prompts):
    """Without session_id, no history is stored."""
    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ResponseCache") as MockCache:
            MockCache.get = AsyncMock(return_value=None)
            MockCache.set = AsyncMock(return_value=True)
            MockCache.store_query_mapping = AsyncMock(return_value=True)
            with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
                MockHistory.get_turns = AsyncMock(return_value=[])
                MockHistory.add_turn = AsyncMock(return_value=True)

                from core.orchestrator.query_handler import QueryHandler

                handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
                await handler.execute("show STATIONS")

    MockHistory.add_turn.assert_not_called()
