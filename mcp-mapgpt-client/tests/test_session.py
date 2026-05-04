"""Tests for SessionManager."""

import time
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client."""
    r = AsyncMock()
    r.exists = AsyncMock(return_value=0)
    r.hset = AsyncMock()
    r.expire = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_create_session(mock_redis):
    """Session created on first call with created_at and TTL."""
    mock_redis.exists.return_value = 0

    with patch("core.session.get_redis", return_value=mock_redis):
        from core.session import SessionManager

        result = await SessionManager.ensure_session("test-123")

    assert result is True
    mock_redis.hset.assert_called_once()
    args = mock_redis.hset.call_args
    assert args[0][0] == "sess:test-123"
    assert args[0][1] == "created_at"
    mock_redis.expire.assert_called_once_with("sess:test-123", 7200)


@pytest.mark.asyncio
async def test_refresh_ttl_existing_session(mock_redis):
    """Existing session only refreshes TTL, does not recreate."""
    mock_redis.exists.return_value = 1

    with patch("core.session.get_redis", return_value=mock_redis):
        from core.session import SessionManager

        result = await SessionManager.ensure_session("existing-456")

    assert result is True
    mock_redis.hset.assert_not_called()
    mock_redis.expire.assert_called_once_with("sess:existing-456", 7200)


@pytest.mark.asyncio
async def test_redis_unavailable():
    """Returns False when Redis is unavailable."""
    with patch("core.session.get_redis", return_value=None):
        from core.session import SessionManager

        result = await SessionManager.ensure_session("no-redis")

    assert result is False


@pytest.mark.asyncio
async def test_redis_exception(mock_redis):
    """Returns False when Redis raises an exception."""
    mock_redis.exists.side_effect = ConnectionError("connection lost")

    with patch("core.session.get_redis", return_value=mock_redis):
        from core.session import SessionManager

        result = await SessionManager.ensure_session("error-789")

    assert result is False
