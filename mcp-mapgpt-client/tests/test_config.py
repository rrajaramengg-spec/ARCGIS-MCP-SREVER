"""Unit tests for ClientConfig."""

import os
import pytest
from unittest.mock import patch
from pydantic import ValidationError

from core.config import ClientConfig

# Environment keys that ClientConfig reads — must be cleared for required-field tests
_CONFIG_ENV_KEYS = [
    "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "DATABASE_URL",
    "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "REDIS_URL",
    "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "ARCGIS_MCP_URL",
    "CORS_ORIGINS", "LOG_LEVEL", "LOG_FORMAT", "LOG_CORRELATION_ENABLED",
    "LLM_MAX_TOKENS", "LLM_TEMPERATURE",
    "EMBEDDING_DIMENSION", "MAX_HISTORY_TURNS", "SESSION_TTL_SECONDS",
    "RATE_LIMIT_PER_MINUTE",
]


def _clean_env():
    """Return env dict with all ClientConfig keys removed."""
    return {k: v for k, v in os.environ.items() if k not in _CONFIG_ENV_KEYS}


class TestClientConfigRequiredFields:
    """Validate that required fields raise ValidationError when missing."""

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            with pytest.raises(ValidationError) as exc_info:
                ClientConfig(
                    azure_openai_endpoint="https://test.openai.azure.com",
                    database_url="postgresql+asyncpg://x:x@localhost/x",
                    _env_file=None,
                )
            errors = exc_info.value.errors()
            field_names = [e["loc"][0] for e in errors]
            assert "azure_openai_api_key" in field_names

    def test_missing_endpoint_raises(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            with pytest.raises(ValidationError) as exc_info:
                ClientConfig(
                    azure_openai_api_key="sk-test",
                    database_url="postgresql+asyncpg://x:x@localhost/x",
                    _env_file=None,
                )
            errors = exc_info.value.errors()
            field_names = [e["loc"][0] for e in errors]
            assert "azure_openai_endpoint" in field_names

    def test_missing_database_url_raises(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            with pytest.raises(ValidationError) as exc_info:
                ClientConfig(
                    azure_openai_api_key="sk-test",
                    azure_openai_endpoint="https://test.openai.azure.com",
                    _env_file=None,
                )
            errors = exc_info.value.errors()
            field_names = [e["loc"][0] for e in errors]
            assert "database_url" in field_names

    def test_all_required_missing_raises(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            with pytest.raises(ValidationError) as exc_info:
                ClientConfig(_env_file=None)
            assert exc_info.value.error_count() >= 3


class TestClientConfigDefaults:
    """Validate that optional fields have correct defaults."""

    def test_defaults(self, mock_config):
        assert mock_config.llm_max_tokens == 4096
        assert mock_config.embedding_dimension == 1536
        assert mock_config.session_ttl_seconds == 7200
        assert mock_config.max_history_turns == 3
        assert mock_config.rate_limit_per_minute == 60
        assert mock_config.log_level == "INFO"
        assert mock_config.log_format == "text"
        assert mock_config.log_correlation_enabled is True
        assert mock_config.azure_openai_api_version == "2025-04-01-preview"
        assert mock_config.azure_openai_deployment == "gpt-5-mini"
        assert mock_config.azure_openai_embedding_deployment == "text-embedding-3-small"
        assert mock_config.redis_url == "redis://localhost:6379/0"
        assert mock_config.celery_broker_url == "redis://localhost:6379/1"
        assert mock_config.celery_result_backend == "redis://localhost:6379/2"
        assert mock_config.cors_origins == "http://localhost:3000"
        assert mock_config.arcgis_mcp_url == ""


class TestClientConfigTypeCoercion:
    """Validate that string env values are coerced to correct types."""

    def test_int_coercion(self):
        config = ClientConfig(
            azure_openai_api_key="sk-test",
            azure_openai_endpoint="https://test.openai.azure.com",
            database_url="postgresql+asyncpg://x:x@localhost/x",
            llm_max_tokens="8192",
            session_ttl_seconds="3600",
            rate_limit_per_minute="120",
            embedding_dimension="768",
            max_history_turns="5",
            _env_file=None,
        )
        assert config.llm_max_tokens == 8192
        assert config.session_ttl_seconds == 3600
        assert config.rate_limit_per_minute == 120
        assert config.embedding_dimension == 768
        assert config.max_history_turns == 5


class TestClientConfigSecretMasking:
    """Validate that secrets are masked in repr output."""

    def test_api_key_not_in_repr(self, mock_config):
        repr_str = repr(mock_config)
        assert "test-key-not-real" not in repr_str

    def test_api_key_accessible(self, mock_config):
        assert mock_config.azure_openai_api_key == "test-key-not-real"


class TestClientConfigLogFormat:
    """Validate log_format and log_correlation_enabled fields."""

    def test_default_log_format_is_text(self):
        config = ClientConfig(
            azure_openai_api_key="sk-test",
            azure_openai_endpoint="https://test.openai.azure.com",
            database_url="postgresql+asyncpg://x:x@localhost/x",
            _env_file=None,
        )
        assert config.log_format == "text"

    def test_json_log_format_via_kwarg(self):
        config = ClientConfig(
            azure_openai_api_key="sk-test",
            azure_openai_endpoint="https://test.openai.azure.com",
            database_url="postgresql+asyncpg://x:x@localhost/x",
            log_format="json",
            _env_file=None,
        )
        assert config.log_format == "json"

    def test_json_log_format_via_env(self):
        with patch.dict(os.environ, {
            "AZURE_OPENAI_API_KEY": "sk-test",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
            "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
            "LOG_FORMAT": "json",
        }, clear=True):
            config = ClientConfig(_env_file=None)
        assert config.log_format == "json"

    def test_default_correlation_enabled(self):
        config = ClientConfig(
            azure_openai_api_key="sk-test",
            azure_openai_endpoint="https://test.openai.azure.com",
            database_url="postgresql+asyncpg://x:x@localhost/x",
            _env_file=None,
        )
        assert config.log_correlation_enabled is True

    def test_correlation_disabled_via_env(self):
        with patch.dict(os.environ, {
            "AZURE_OPENAI_API_KEY": "sk-test",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
            "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
            "LOG_CORRELATION_ENABLED": "false",
        }, clear=True):
            config = ClientConfig(_env_file=None)
        assert config.log_correlation_enabled is False
