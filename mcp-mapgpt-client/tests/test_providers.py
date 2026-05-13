"""Unit tests for dependency providers (core/providers.py)."""

import pytest

from core import providers


class TestOrchestratorProvider:
    """Tests for orchestrator provider lifecycle."""

    def setup_method(self):
        """Reset provider state before each test."""
        providers._orchestrator = None

    def test_get_before_set_raises(self):
        """get_orchestrator raises RuntimeError before initialization."""
        with pytest.raises(RuntimeError, match="Orchestrator not initialized"):
            providers.get_orchestrator()

    def test_set_then_get(self):
        """set_orchestrator followed by get_orchestrator returns the same instance."""
        sentinel = object()
        providers.set_orchestrator(sentinel)
        assert providers.get_orchestrator() is sentinel

    def test_set_overwrites(self):
        """set_orchestrator can be called multiple times."""
        first = object()
        second = object()
        providers.set_orchestrator(first)
        providers.set_orchestrator(second)
        assert providers.get_orchestrator() is second


class TestRAGServiceProvider:
    """Tests for RAG service provider lifecycle."""

    def setup_method(self):
        """Reset provider state before each test."""
        providers._rag_service = None

    def test_get_before_set_raises(self):
        """get_rag_service raises RuntimeError before initialization."""
        with pytest.raises(RuntimeError, match="RAGService not initialized"):
            providers.get_rag_service()

    def test_set_then_get(self):
        """set_rag_service followed by get_rag_service returns the same instance."""
        sentinel = object()
        providers.set_rag_service(sentinel)
        assert providers.get_rag_service() is sentinel

    def test_set_overwrites(self):
        """set_rag_service can be called multiple times."""
        first = object()
        second = object()
        providers.set_rag_service(first)
        providers.set_rag_service(second)
        assert providers.get_rag_service() is second


class TestConfigProvider:
    """Tests for config provider lifecycle."""

    def setup_method(self):
        """Reset provider state before each test."""
        providers._config = None

    def test_get_before_set_raises(self):
        """get_config raises RuntimeError before initialization."""
        with pytest.raises(RuntimeError, match="ClientConfig not initialized"):
            providers.get_config()

    def test_set_then_get(self, mock_config):
        """set_config followed by get_config returns the same instance."""
        providers.set_config(mock_config)
        assert providers.get_config() is mock_config

    def test_set_overwrites(self, mock_config):
        """set_config can be called multiple times."""
        from core.config import ClientConfig

        other = ClientConfig(
            azure_openai_api_key="other-key",
            azure_openai_endpoint="https://other.openai.azure.com",
            database_url="postgresql+asyncpg://x:x@localhost/x",
            _env_file=None,
        )
        providers.set_config(mock_config)
        providers.set_config(other)
        assert providers.get_config() is other
