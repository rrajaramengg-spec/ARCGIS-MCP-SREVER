"""Tests for history injection into QueryHandler.plan()."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_llm_response(plan_dict):
    """Create a mock LLM response with JSON content."""
    resp = MagicMock()
    resp.content = json.dumps(plan_dict)
    resp.tool_calls = []
    resp.has_tool_calls = False
    return resp


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=_make_llm_response({"action": "query", "query": [{"layer": "STATIONS"}], "message": "ok"})
    )
    return llm


@pytest.fixture
def mock_mcp():
    mcp = AsyncMock()
    mcp.list_tools = AsyncMock(return_value=[])
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
async def test_plan_without_history(mock_mcp, mock_llm, prompts):
    """First query — no history, message array is [system, user]."""
    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
            MockHistory.get_turns = AsyncMock(return_value=[])

            from core.orchestrator.query_handler import QueryHandler

            handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
            result = await handler.plan("show STATIONS", session_id="s1")

    assert result["action"] == "query"


@pytest.mark.asyncio
async def test_plan_with_one_turn(mock_mcp, mock_llm, prompts):
    """One prior turn — message array is [system, user_1, assistant_1, current_user]."""
    history = [
        {"role": "user", "content": "show STATIONS"},
        {"role": "assistant", "content": '{"action":"query","query":[{"layer":"STATIONS"}]}'},
    ]

    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
            MockHistory.get_turns = AsyncMock(return_value=history)

            from core.orchestrator.query_handler import QueryHandler

            handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
            result = await handler.plan("now show for ohio", session_id="s1")

    # LLM was called with history injected
    call_args = mock_llm.complete.call_args
    messages = call_args[0][0]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "show STATIONS"
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"  # current query


@pytest.mark.asyncio
async def test_plan_with_three_turns(mock_mcp, mock_llm, prompts):
    """Three prior turns — full message array."""
    history = []
    for i in range(3):
        history.append({"role": "user", "content": f"query {i}"})
        history.append({"role": "assistant", "content": json.dumps({"action": "query", "query": [{"layer": f"L{i}"}]})})

    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
            MockHistory.get_turns = AsyncMock(return_value=history)

            from core.orchestrator.query_handler import QueryHandler

            handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
            await handler.plan("compare results", session_id="s1")

    call_args = mock_llm.complete.call_args
    messages = call_args[0][0]
    # system + 6 history entries + current user = 8 messages
    assert len(messages) == 8
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"


@pytest.mark.asyncio
async def test_plan_history_failure_fallback(mock_mcp, mock_llm, prompts):
    """History retrieval failure — plan proceeds without history."""
    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        with patch("core.orchestrator.query_handler.ConversationHistory") as MockHistory:
            MockHistory.get_turns = AsyncMock(side_effect=Exception("Redis down"))

            from core.orchestrator.query_handler import QueryHandler

            handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
            result = await handler.plan("show STATIONS", session_id="s1")

    assert result["action"] == "query"


@pytest.mark.asyncio
async def test_plan_without_session_id(mock_mcp, mock_llm, prompts):
    """No session_id — no history lookup, standard behavior."""
    with patch("core.orchestrator.query_handler.build_rag_context", return_value=("ctx", [])):
        from core.orchestrator.query_handler import QueryHandler

        handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts=prompts, tools_cache=[])
        result = await handler.plan("show STATIONS")

    assert result["action"] == "query"
