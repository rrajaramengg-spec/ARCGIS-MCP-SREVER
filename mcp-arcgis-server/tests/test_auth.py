"""Tests for auth concurrency safety."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_arcgis_server.arcgis.auth import GISAuthManager
from mcp_arcgis_server.config import ServerConfig


def _make_config(**overrides) -> ServerConfig:
    """Create a ServerConfig with test defaults."""
    defaults = {
        "ARCGIS_PORTAL_URL": "",
        "ARCGIS_USERNAME": "",
        "ARCGIS_PASSWORD": "",
    }
    defaults.update(overrides)
    return ServerConfig(**{k.lower().replace("arcgis_", ""): v for k, v in defaults.items()})


class TestAuthConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_initialize_runs_once(self):
        """Multiple concurrent initialize() calls should only init once."""
        call_count = 0

        def mock_init_gis(self_ref):
            nonlocal call_count
            call_count += 1
            self_ref._gis = MagicMock()  # Simulate successful init

        config = _make_config()
        auth = GISAuthManager(config)
        auth._portal_url = "https://portal.example.com"
        auth._username = "user"
        auth._password = "pass"

        with patch.object(GISAuthManager, "_initialize_gis", lambda self: mock_init_gis(self)):
            await asyncio.gather(
                auth.initialize(),
                auth.initialize(),
                auth.initialize(),
            )

        # Only 1 actual init should have run (others see _gis is not None)
        assert call_count == 1
        assert auth._gis is not None

    @pytest.mark.asyncio
    async def test_initialize_skips_when_already_initialized(self):
        config = _make_config()
        auth = GISAuthManager(config)
        auth._gis = MagicMock()  # Already initialized

        with patch.object(GISAuthManager, "_initialize_gis") as mock:
            await auth.initialize()
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_resets_and_reinitializes(self):
        config = _make_config()
        auth = GISAuthManager(config)
        auth._portal_url = "https://portal.example.com"
        auth._username = "user"
        auth._password = "pass"
        auth._gis = MagicMock()  # Already initialized

        new_gis = MagicMock()

        def mock_init(self_ref):
            self_ref._gis = new_gis

        cache_cleared = False

        def clear_cache():
            nonlocal cache_cleared
            cache_cleared = True

        with patch.object(GISAuthManager, "_initialize_gis", lambda self: mock_init(self)):
            await auth.refresh(clear_layer_cache_fn=clear_cache)

        assert auth._gis is new_gis
        assert cache_cleared

    @pytest.mark.asyncio
    async def test_config_passed_to_auth(self):
        config = ServerConfig(
            portal_url="https://portal.test.com",
            username="testuser",
            password="testpass",
            verify_ssl=False,
            token_url="https://token.test.com/generate",
            server_url="https://server.test.com",
        )

        auth = GISAuthManager(config)
        assert auth._portal_url == "https://portal.test.com"
        assert auth._username == "testuser"
        assert auth._password == "testpass"
        assert auth._verify_ssl is False
        assert auth._token_url == "https://token.test.com/generate"
        assert auth._server_url == "https://server.test.com"
