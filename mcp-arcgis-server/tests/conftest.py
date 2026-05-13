"""Shared test fixtures for mcp-arcgis-server tests."""

import pytest

from mcp_arcgis_server.config import ServerConfig


@pytest.fixture
def default_config() -> ServerConfig:
    """Return a ServerConfig with empty/default test values."""
    return ServerConfig()


def make_config(**kwargs) -> ServerConfig:
    """Create a ServerConfig with specified overrides.

    Convenience for tests that need specific portal_url, username, etc.
    """
    return ServerConfig(**kwargs)
