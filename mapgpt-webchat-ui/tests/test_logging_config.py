"""Tests for mapgpt-webchat-ui logging configuration."""

import logging
import os
from unittest.mock import patch


class TestWebchatLoggingSetup:
    """Verify setup_logging supports text and JSON formats."""

    def test_text_format_default(self):
        with patch.dict(os.environ, {}, clear=True):
            from logging_config import setup_logging
            setup_logging("test-webchat")
        root = logging.getLogger()
        assert len(root.handlers) >= 1
        fmt = root.handlers[0].formatter
        assert isinstance(fmt, logging.Formatter)

    def test_json_format(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}, clear=True):
            from logging_config import setup_logging
            setup_logging("test-webchat")
        root = logging.getLogger()
        handler = root.handlers[0]
        from pythonjsonlogger.json import JsonFormatter
        assert isinstance(handler.formatter, JsonFormatter)

    def test_log_level_from_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=True):
            from logging_config import setup_logging
            setup_logging("test-webchat")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
