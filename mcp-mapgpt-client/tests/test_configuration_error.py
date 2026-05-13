"""Unit tests for ConfigurationError."""

import pytest
from pydantic import ValidationError

from core.config import ClientConfig
from core.exceptions import ConfigurationError, MapGPTError


class TestConfigurationError:
    """Validate ConfigurationError follows MapGPTError pattern."""

    def test_is_mapgpt_error(self):
        exc = ConfigurationError("test message")
        assert isinstance(exc, MapGPTError)

    def test_code(self):
        exc = ConfigurationError("test message")
        assert exc.code == "CONFIGURATION_ERROR"

    def test_status_code(self):
        exc = ConfigurationError("test message")
        assert exc.status_code == 500

    def test_message(self):
        exc = ConfigurationError("missing AZURE_OPENAI_API_KEY")
        assert exc.message == "missing AZURE_OPENAI_API_KEY"
        assert str(exc) == "missing AZURE_OPENAI_API_KEY"

    def test_wraps_validation_error(self):
        """Simulate the main.py pattern of wrapping ValidationError."""
        try:
            ClientConfig(_env_file=None)
        except ValidationError as ve:
            exc = ConfigurationError(
                f"Invalid configuration — {ve.error_count()} error(s): {ve}"
            )
            exc.__cause__ = ve

            assert isinstance(exc, ConfigurationError)
            assert isinstance(exc.__cause__, ValidationError)
            assert "error(s)" in exc.message
            assert exc.code == "CONFIGURATION_ERROR"
