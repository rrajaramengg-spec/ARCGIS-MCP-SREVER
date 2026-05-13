"""Tests for the user-feedback API route."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_app():
    """Create a minimal test app with the feedback route."""
    from fastapi import FastAPI
    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_thumbs_up_promotes(mock_app):
    """Thumbs up → promoted action."""
    with patch("api.routes.ResponseCache") as MockCache:
        MockCache.get_cache_key_for_query = AsyncMock(return_value="fcache:q:h")
        MockCache.promote = AsyncMock(return_value=True)

        async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/mapgpt/v1/user-feedback",
                json={"session_id": "s1", "query_id": "q1", "feedback": "up"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "promoted"
    MockCache.promote.assert_called_once_with("fcache:q:h")


@pytest.mark.asyncio
async def test_thumbs_down_evicts_unpromoted(mock_app):
    """Thumbs down on unpromoted entry → evicted."""
    with patch("api.routes.ResponseCache") as MockCache:
        MockCache.get_cache_key_for_query = AsyncMock(return_value="fcache:q:h")
        MockCache.evict = AsyncMock(return_value="evicted")

        async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/mapgpt/v1/user-feedback",
                json={"session_id": "s1", "query_id": "q1", "feedback": "down"},
            )

    assert resp.status_code == 200
    assert resp.json()["action"] == "evicted"


@pytest.mark.asyncio
async def test_thumbs_down_protected_on_promoted(mock_app):
    """Thumbs down on promoted entry → protected."""
    with patch("api.routes.ResponseCache") as MockCache:
        MockCache.get_cache_key_for_query = AsyncMock(return_value="fcache:q:h")
        MockCache.evict = AsyncMock(return_value="protected")

        async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/mapgpt/v1/user-feedback",
                json={"session_id": "s1", "query_id": "q1", "feedback": "down"},
            )

    assert resp.status_code == 200
    assert resp.json()["action"] == "protected"


@pytest.mark.asyncio
async def test_no_cache_entry(mock_app):
    """Feedback for non-cached response → no_cache_entry."""
    with patch("api.routes.ResponseCache") as MockCache:
        MockCache.get_cache_key_for_query = AsyncMock(return_value=None)

        async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/mapgpt/v1/user-feedback",
                json={"session_id": "s1", "query_id": "q1", "feedback": "up"},
            )

    assert resp.status_code == 200
    assert resp.json()["action"] == "no_cache_entry"


@pytest.mark.asyncio
async def test_invalid_feedback_value(mock_app):
    """Invalid feedback value → 422."""
    async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/mapgpt/v1/user-feedback",
            json={"session_id": "s1", "query_id": "q1", "feedback": "maybe"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_fields(mock_app):
    """Missing required fields → 422."""
    async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/mapgpt/v1/user-feedback",
            json={"feedback": "up"},
        )

    assert resp.status_code == 422
