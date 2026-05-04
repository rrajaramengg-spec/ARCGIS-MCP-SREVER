"""Tests for ServerConfig."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from mcp_arcgis_server.config import ServerConfig


class TestServerConfigDefaults:
    """Verify default values when no env vars are set."""

    def test_default_host(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.mcp_host == "0.0.0.0"

    def test_default_port(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.mcp_port == 8001

    def test_default_thread_pool(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.thread_pool_max_workers == 8

    def test_default_cache_size(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.layer_cache_max_size == 100

    def test_default_max_results(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.default_max_results == 200

    def test_default_tools_disabled_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.disabled_tools_list == []

    def test_default_verify_ssl_true(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.verify_ssl is True

    def test_default_empty_strings(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        assert config.portal_url == ""
        assert config.username == ""
        assert config.password == ""
        assert config.token_url == ""
        assert config.server_url == ""
        assert config.geocode_url == ""


class TestServerConfigEnvParsing:
    """Verify env var parsing."""

    def test_custom_host_and_port(self):
        with patch.dict(os.environ, {"ARCGIS_MCP_HOST": "127.0.0.1", "ARCGIS_MCP_PORT": "9000"}, clear=True):
            config = ServerConfig()
        assert config.mcp_host == "127.0.0.1"
        assert config.mcp_port == 9000

    def test_custom_thread_pool_workers(self):
        with patch.dict(os.environ, {"ARCGIS_THREAD_POOL_MAX_WORKERS": "16"}, clear=True):
            config = ServerConfig()
        assert config.thread_pool_max_workers == 16

    def test_custom_cache_size(self):
        with patch.dict(os.environ, {"ARCGIS_LAYER_CACHE_MAX_SIZE": "50"}, clear=True):
            config = ServerConfig()
        assert config.layer_cache_max_size == 50

    def test_verify_ssl_false(self):
        with patch.dict(os.environ, {"ARCGIS_VERIFY_SSL": "false"}, clear=True):
            config = ServerConfig()
        assert config.verify_ssl is False

    def test_portal_url_parsed(self):
        with patch.dict(os.environ, {"ARCGIS_PORTAL_URL": "https://gis.example.com/portal"}, clear=True):
            config = ServerConfig()
        assert config.portal_url == "https://gis.example.com/portal"


class TestServerConfigToolsDisabled:
    """Verify comma-separated tools_disabled parsing."""

    def test_single_tool(self):
        with patch.dict(os.environ, {"ARCGIS_TOOLS_DISABLED": "geocode"}, clear=True):
            config = ServerConfig()
        assert config.disabled_tools_list == ["geocode"]

    def test_multiple_tools(self):
        with patch.dict(os.environ, {"ARCGIS_TOOLS_DISABLED": "geocode,reversegeocode"}, clear=True):
            config = ServerConfig()
        assert config.disabled_tools_list == ["geocode", "reversegeocode"]

    def test_whitespace_stripped(self):
        with patch.dict(os.environ, {"ARCGIS_TOOLS_DISABLED": "geocode, reversegeocode , buffer_and_query"}, clear=True):
            config = ServerConfig()
        assert config.disabled_tools_list == ["geocode", "reversegeocode", "buffer_and_query"]

    def test_empty_string(self):
        with patch.dict(os.environ, {"ARCGIS_TOOLS_DISABLED": ""}, clear=True):
            config = ServerConfig()
        assert config.disabled_tools_list == []

    def test_trailing_comma(self):
        with patch.dict(os.environ, {"ARCGIS_TOOLS_DISABLED": "geocode,"}, clear=True):
            config = ServerConfig()
        assert config.disabled_tools_list == ["geocode"]


class TestServerConfigValidation:
    """Verify validation rejects invalid values."""

    def test_invalid_port_rejected(self):
        with patch.dict(os.environ, {"ARCGIS_MCP_PORT": "not_a_number"}, clear=True):
            with pytest.raises(ValidationError):
                ServerConfig()

    def test_invalid_workers_rejected(self):
        with patch.dict(os.environ, {"ARCGIS_THREAD_POOL_MAX_WORKERS": "abc"}, clear=True):
            with pytest.raises(ValidationError):
                ServerConfig()
