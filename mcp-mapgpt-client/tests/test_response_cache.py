"""Tests for ResponseCache."""

import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client."""
    r = AsyncMock()
    r.hget = AsyncMock(return_value=None)
    r.hset = AsyncMock()
    r.expire = AsyncMock()
    r.delete = AsyncMock()
    r.set = AsyncMock()
    r.get = AsyncMock(return_value=None)
    return r


SAMPLE_RESPONSE = {
    "action": "query",
    "message": "Found 3 PSAPs",
    "data": {"results": []},
    "execution_time_ms": 1234.5,
}


@pytest.mark.asyncio
async def test_cache_set_and_get(mock_redis):
    """set() stores JSON hash, get() retrieves parsed response."""
    mock_redis.hget.return_value = json.dumps(SAMPLE_RESPONSE)

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        from core.response_cache import ResponseCache

        await ResponseCache.set("show psap", "abc123", SAMPLE_RESPONSE)

    mock_redis.hset.assert_called_once()
    call_kwargs = mock_redis.hset.call_args
    mapping = call_kwargs[1]["mapping"]
    assert json.loads(mapping["response"]) == SAMPLE_RESPONSE
    assert mapping["promoted"] == "false"
    mock_redis.expire.assert_called_once()

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        result = await ResponseCache.get("show psap", "abc123")

    assert result == SAMPLE_RESPONSE


@pytest.mark.asyncio
async def test_cache_miss(mock_redis):
    """get() returns None when key doesn't exist."""
    mock_redis.hget.return_value = None

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        from core.response_cache import ResponseCache

        result = await ResponseCache.get("unknown query", "xyz")

    assert result is None


@pytest.mark.asyncio
async def test_promote(mock_redis):
    """promote() sets promoted=true and extends TTL."""
    with patch("core.response_cache.get_redis", return_value=mock_redis):
        from core.response_cache import ResponseCache

        result = await ResponseCache.promote("fcache:q:h")

    assert result is True
    mock_redis.hset.assert_called_once_with("fcache:q:h", "promoted", "true")
    mock_redis.expire.assert_called_once_with("fcache:q:h", 864000)


@pytest.mark.asyncio
async def test_evict_unpromoted(mock_redis):
    """evict() deletes entry when promoted=false."""
    mock_redis.hget.return_value = "false"

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        from core.response_cache import ResponseCache

        result = await ResponseCache.evict("fcache:q:h")

    assert result == "evicted"
    mock_redis.delete.assert_called_once_with("fcache:q:h")


@pytest.mark.asyncio
async def test_evict_promoted_protected(mock_redis):
    """evict() does NOT delete when promoted=true."""
    mock_redis.hget.return_value = "true"

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        from core.response_cache import ResponseCache

        result = await ResponseCache.evict("fcache:q:h")

    assert result == "protected"
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_evict_no_entry(mock_redis):
    """evict() returns no_cache_entry when key doesn't exist."""
    mock_redis.hget.return_value = None

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        from core.response_cache import ResponseCache

        result = await ResponseCache.evict("fcache:nonexistent:key")

    assert result == "no_cache_entry"


@pytest.mark.asyncio
async def test_redis_unavailable():
    """All methods degrade gracefully when Redis unavailable."""
    with patch("core.response_cache.get_redis", return_value=None):
        from core.response_cache import ResponseCache

        assert await ResponseCache.get("q", "h") is None
        assert await ResponseCache.set("q", "h", {}) is False
        assert await ResponseCache.promote("k") is False
        assert await ResponseCache.evict("k") == "no_cache_entry"
        assert await ResponseCache.store_query_mapping("s", "q", "k") is False
        assert await ResponseCache.get_cache_key_for_query("s", "q") is None


@pytest.mark.asyncio
async def test_query_mapping(mock_redis):
    """store_query_mapping and get_cache_key_for_query round-trip."""
    mock_redis.get.return_value = "fcache:show psap:abc123"

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        from core.response_cache import ResponseCache

        await ResponseCache.store_query_mapping("sess1", "qid1", "fcache:show psap:abc123")

    mock_redis.set.assert_called_once()
    args = mock_redis.set.call_args
    assert args[0][0] == "qmap:sess1:qid1"
    assert args[0][1] == "fcache:show psap:abc123"

    with patch("core.response_cache.get_redis", return_value=mock_redis):
        key = await ResponseCache.get_cache_key_for_query("sess1", "qid1")

    assert key == "fcache:show psap:abc123"
