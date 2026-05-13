"""Tests for ConversationHistory."""

import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client."""
    r = AsyncMock()
    r.rpush = AsyncMock()
    r.ltrim = AsyncMock()
    r.expire = AsyncMock()
    r.lrange = AsyncMock(return_value=[])
    return r


SIMPLE_PLAN = {
    "action": "query",
    "query": [{"type": "where", "layer": "PSAP", "layer_url": "https://example.com/PSAP", "where": "COUNTY = 'Madison'"}],
    "message": "Querying PSAP in Madison County",
}


@pytest.mark.asyncio
async def test_add_turn(mock_redis):
    """Turn stored as user + assistant entries in Redis list."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        result = await ConversationHistory.add_turn("s1", "show psap", SIMPLE_PLAN)

    assert result is True
    mock_redis.rpush.assert_called_once()
    args = mock_redis.rpush.call_args[0]
    assert args[0] == "hist:s1"
    user_entry = json.loads(args[1])
    assert user_entry["role"] == "user"
    assert user_entry["content"] == "show psap"
    assistant_entry = json.loads(args[2])
    assert assistant_entry["role"] == "assistant"
    # Plan JSON stored, not a message string
    plan = json.loads(assistant_entry["content"])
    assert plan["action"] == "query"
    mock_redis.ltrim.assert_called_once_with("hist:s1", -6, -1)
    mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_get_turns(mock_redis):
    """Returns parsed entries in chronological order."""
    entries = [
        json.dumps({"role": "user", "content": "q1"}),
        json.dumps({"role": "assistant", "content": '{"action":"query"}'}),
    ]
    mock_redis.lrange.return_value = entries

    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        turns = await ConversationHistory.get_turns("s1")

    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_three_turn_cap_eviction(mock_redis):
    """ltrim keeps only last 6 entries (3 turns)."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        await ConversationHistory.add_turn("s1", "q1", SIMPLE_PLAN)

    mock_redis.ltrim.assert_called_once_with("hist:s1", -6, -1)


@pytest.mark.asyncio
async def test_plan_trimming_strips_layer_url():
    """Plans over 500 tokens get layer_url stripped first."""
    from core.history import _trim_plan, _count_tokens

    # Build a plan with a very long layer_url to push over 500 tokens
    big_plan = {
        "action": "query",
        "query": [
            {
                "type": "where",
                "layer": f"LAYER_{i}",
                "layer_url": f"https://example.com/very/long/arcgis/rest/services/MapServer/{i}" * 5,
                "where": f"FIELD_{i} = 'value'",
                "fields": [f"F{j}" for j in range(20)],
            }
            for i in range(5)
        ],
        "message": "test query",
    }
    trimmed_json = _trim_plan(big_plan)
    trimmed = json.loads(trimmed_json)
    assert _count_tokens(trimmed_json) <= 500
    # Structure preserved
    assert trimmed["action"] == "query"
    assert "query" in trimmed
    # layer_url should be stripped
    for node in trimmed["query"]:
        assert "layer_url" not in node


@pytest.mark.asyncio
async def test_plan_within_budget_stored_as_is():
    """Plans under 500 tokens stored without modification."""
    from core.history import _trim_plan, _count_tokens

    plan_json = _trim_plan(SIMPLE_PLAN)
    plan = json.loads(plan_json)
    assert plan["action"] == "query"
    assert plan["query"][0]["layer_url"] == "https://example.com/PSAP"


@pytest.mark.asyncio
async def test_empty_history(mock_redis):
    """Empty list returned for session with no history."""
    mock_redis.lrange.return_value = []

    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        turns = await ConversationHistory.get_turns("empty-session")

    assert turns == []


@pytest.mark.asyncio
async def test_redis_unavailable_add():
    """add_turn returns False when Redis is unavailable."""
    with patch("core.history.get_redis", return_value=None):
        from core.history import ConversationHistory

        result = await ConversationHistory.add_turn("s1", "q", {"action": "query"})

    assert result is False


@pytest.mark.asyncio
async def test_redis_unavailable_get():
    """get_turns returns empty list when Redis is unavailable."""
    with patch("core.history.get_redis", return_value=None):
        from core.history import ConversationHistory

        turns = await ConversationHistory.get_turns("s1")

    assert turns == []


@pytest.mark.asyncio
async def test_plan_json_stored_not_message(mock_redis):
    """Assistant entry contains plan JSON, not post-execution message."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        plan = {"action": "query", "query": [{"type": "where", "layer": "PSAP"}], "message": "Querying PSAP"}
        await ConversationHistory.add_turn("s1", "show psap", plan)

    args = mock_redis.rpush.call_args[0]
    assistant_entry = json.loads(args[2])
    stored_plan = json.loads(assistant_entry["content"])
    assert "action" in stored_plan
    assert "query" in stored_plan


@pytest.mark.asyncio
async def test_compare_contrast_three_turns(mock_redis):
    """Three turns of history enable compare/contrast pattern."""
    turns_data = []
    for i, q in enumerate(["show psap in madison", "show fire stations", "compare with first"]):
        turns_data.append(json.dumps({"role": "user", "content": q}))
        turns_data.append(json.dumps({"role": "assistant", "content": json.dumps({"action": "query", "query": [{"layer": f"L{i}"}]})}))
    mock_redis.lrange.return_value = turns_data

    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        turns = await ConversationHistory.get_turns("s1")

    assert len(turns) == 6
    assert turns[0]["content"] == "show psap in madison"  # Q1 still available at Q3
    assert turns[4]["content"] == "compare with first"
