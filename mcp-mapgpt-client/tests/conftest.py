"""Shared test fixtures for mcp-mapgpt-client tests."""

import pytest

from core.config import ClientConfig


@pytest.fixture
def mock_config() -> ClientConfig:
    """Return a ClientConfig with safe test values.

    Uses ``_env_file=None`` to prevent reading from ``.env``.
    All required fields are provided with test-safe defaults.
    """
    return ClientConfig(
        azure_openai_api_key="test-key-not-real",
        azure_openai_endpoint="https://test.openai.azure.com",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        celery_broker_url="redis://localhost:6379/1",
        celery_result_backend="redis://localhost:6379/2",
        arcgis_mcp_url="",
        cors_origins="http://localhost:3000",
        azure_openai_api_version="2025-04-01-preview",
        azure_openai_deployment="gpt-5-mini",
        azure_openai_embedding_deployment="text-embedding-3-small",
        llm_max_tokens=4096,
        embedding_dimension=1536,
        session_ttl_seconds=7200,
        max_history_turns=3,
        rate_limit_per_minute=60,
        log_level="INFO",
        log_format="text",
        log_correlation_enabled=True,
        arcgis_max_concurrent=10,
        node_retry_max_attempts=3,
        _env_file=None,
    )
