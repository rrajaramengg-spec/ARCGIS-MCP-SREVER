"""Unit tests for RAGService (core/rag/service.py)."""

import pytest
from unittest.mock import AsyncMock, patch

from core.contracts import IRAGService
from core.rag.service import RAGService


class TestRAGService:
    """Tests for RAGService delegation and contract conformance."""

    def test_satisfies_protocol(self):
        """RAGService satisfies the IRAGService protocol."""
        assert isinstance(RAGService(), IRAGService)

    @pytest.mark.asyncio
    async def test_build_context_delegates(self):
        """build_context delegates to prompt.build_rag_context."""
        expected = ("context string", [{"layer": "test"}])
        with patch(
            "core.rag.service.build_rag_context",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock:
            svc = RAGService()
            result = await svc.build_context("test query")
            assert result == expected
            mock.assert_awaited_once_with("test query")

    @pytest.mark.asyncio
    async def test_ingest_layers_delegates(self):
        """ingest_layers delegates to ingestion.ingest_layers."""
        expected = {"layers": 5, "fields": 20}
        with patch(
            "core.rag.service._ingest_layers",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock:
            svc = RAGService()
            result = await svc.ingest_layers([{"name": "layer1"}])
            assert result == expected
            mock.assert_awaited_once_with([{"name": "layer1"}])

    @pytest.mark.asyncio
    async def test_ingest_query_patterns_delegates(self):
        """ingest_query_patterns delegates to ingestion.ingest_query_patterns."""
        expected = {"patterns": 10}
        with patch(
            "core.rag.service._ingest_query_patterns",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock:
            svc = RAGService()
            result = await svc.ingest_query_patterns(
                [{"pattern": "p1"}], replace=True
            )
            assert result == expected
            mock.assert_awaited_once_with([{"pattern": "p1"}], True)

    @pytest.mark.asyncio
    async def test_mockable_for_testing(self):
        """RAGService can be replaced with AsyncMock in tests."""
        mock_svc = AsyncMock(spec=RAGService)
        mock_svc.build_context.return_value = ("ctx", [])
        result = await mock_svc.build_context("q")
        assert result == ("ctx", [])
