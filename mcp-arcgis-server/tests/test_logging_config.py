"""Tests for mcp-arcgis-server logging configuration."""

import json
import logging
import os
from io import StringIO
from unittest.mock import patch

import pytest

from mcp_arcgis_server.config import ServerConfig
from mcp_arcgis_server.logging_config import setup_logging


class TestServerLoggingSetup:
    """Verify setup_logging configures logging based on ServerConfig."""

    def test_text_format_default(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        setup_logging("test-server", config=config)
        root = logging.getLogger()
        assert len(root.handlers) == 1
        fmt = root.handlers[0].formatter
        assert isinstance(fmt, logging.Formatter)
        assert "%(asctime)s" in fmt._fmt

    def test_json_format(self):
        with patch.dict(os.environ, {"ARCGIS_LOG_FORMAT": "json"}, clear=True):
            config = ServerConfig()
        setup_logging("test-server", config=config)
        root = logging.getLogger()
        handler = root.handlers[0]
        from pythonjsonlogger.json import JsonFormatter
        assert isinstance(handler.formatter, JsonFormatter)

    def test_json_output_valid(self):
        with patch.dict(os.environ, {"ARCGIS_LOG_FORMAT": "json"}, clear=True):
            config = ServerConfig()
        stream = StringIO()
        setup_logging("test-server", config=config)
        root = logging.getLogger()
        root.handlers[0].stream = stream

        logging.getLogger("test.json").info("test message")
        output = stream.getvalue().strip()
        line = next((l for l in output.split("\n") if "test message" in l), None)
        assert line is not None
        parsed = json.loads(line)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "test message"

    def test_log_level_from_config(self):
        with patch.dict(os.environ, {"ARCGIS_LOG_LEVEL": "DEBUG"}, clear=True):
            config = ServerConfig()
        setup_logging("test-server", config=config)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_noisy_loggers_suppressed(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig()
        setup_logging("test-server", config=config)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING

    def test_default_config_when_none(self):
        """When config=None, setup_logging creates a default ServerConfig."""
        setup_logging("test-server", config=None)
        root = logging.getLogger()
        assert len(root.handlers) == 1
