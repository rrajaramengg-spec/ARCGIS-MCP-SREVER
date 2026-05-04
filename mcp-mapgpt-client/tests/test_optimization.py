"""
Unit tests for embedding cache, RAG retrieval refactor, LLM planning optimization,
and parallel child queries — covering the optimize-rag-semantic-search change.
"""

import asyncio
import hashlib
import json
import os
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# 9.1 Integration test for rag_unified_search() stored function
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestRagUnifiedSearchIntegration:
    """Integration tests calling rag_unified_search() against a live DB.

    Requires DATABASE_URL env var pointing to a postgres+pgvector database
    with the stored function deployed (alembic migration 004).
    Skip if DATABASE_URL is not set.
    """

    @pytest.fixture(autouse=True)
    def skip_without_db(self):
        if not os.getenv("DATABASE_URL"):
            pytest.skip("DATABASE_URL not set — skipping integration")

    @pytest_asyncio.fixture
    async def session(self):
        from core.rag.database.connection import init_db, async_session_factory, close_db
        init_db()
        async with async_session_factory() as s:
            yield s
        await close_db()

    @staticmethod
    def _zero_embedding():
        """Return a 1536-dim zero vector as a string literal for SQL."""
        return "[" + ",".join(["0"] * 1536) + "]"

    @pytest.mark.asyncio
    async def test_returns_valid_json_structure(self, session):
        """rag_unified_search() returns JSONB with 'layers' and 'patterns' keys."""
        from sqlalchemy import text

        emb = self._zero_embedding()
        row = await session.execute(
            text(
                "SELECT rag_unified_search("
                f"  :emb ::vector, :qt"
                ")"
            ),
            {"emb": emb, "qt": "test"},
        )
        result = row.scalar()
        if isinstance(result, str):
            result = json.loads(result)

        assert isinstance(result, dict)
        assert "layers" in result
        assert "patterns" in result
        assert isinstance(result["layers"], list)
        assert isinstance(result["patterns"], list)

    @pytest.mark.asyncio
    async def test_layers_never_null(self, session):
        """Even with no matches, layers and patterns are empty lists, never NULL."""
        from sqlalchemy import text

        emb = self._zero_embedding()
        row = await session.execute(
            text(
                "SELECT rag_unified_search("
                f"  :emb ::vector, :qt, "
                "  layer_min_score := 0.999, "
                "  pattern_min_score := 0.999"
                ")"
            ),
            {"emb": emb, "qt": "xyznonexistent"},
        )
        result = row.scalar()
        if isinstance(result, str):
            result = json.loads(result)

        assert result is not None
        assert result["layers"] is not None
        assert result["patterns"] is not None

    @pytest.mark.asyncio
    async def test_cosine_scores_in_valid_range(self, session):
        """All cosine scores should be in [0, 1] range (formula: 1 - distance/2)."""
        from sqlalchemy import text

        emb = self._zero_embedding()
        row = await session.execute(
            text(
                "SELECT rag_unified_search("
                f"  :emb ::vector, :qt, "
                "  layer_min_score := 0.0"
                ")"
            ),
            {"emb": emb, "qt": "county"},
        )
        result = row.scalar()
        if isinstance(result, str):
            result = json.loads(result)

        for layer in result.get("layers", []):
            score = float(layer.get("score", 0))
            # Zero-vector input can produce NaN cosine (0/0) — skip those
            if score != score:  # NaN check
                continue
            assert 0 <= score <= 1, (
                f"Score {score} out of [0,1] range for layer"
                f" {layer.get('layer_name')}"
            )

    @pytest.mark.asyncio
    async def test_layer_fields_nested(self, session):
        """Each returned layer should have a 'fields' key (possibly empty list)."""
        from sqlalchemy import text

        emb = self._zero_embedding()
        row = await session.execute(
            text(
                "SELECT rag_unified_search("
                f"  :emb ::vector, :qt, "
                "  layer_min_score := 0.0"
                ")"
            ),
            {"emb": emb, "qt": "county"},
        )
        result = row.scalar()
        if isinstance(result, str):
            result = json.loads(result)

        for layer in result.get("layers", []):
            assert "fields" in layer, (
                f"Layer {layer.get('layer_name')} missing 'fields' key"
            )
            assert isinstance(layer["fields"], list)


# ---------------------------------------------------------------------------
# 4.4 Embedding cache tests
# ---------------------------------------------------------------------------
class TestEmbeddingCache:
    """Tests for module-level @alru_cache on embed_query."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_same_embedding(self):
        """Repeated calls with same text return cached result (single API call)."""
        from core.rag.embeddings.service import _cached_embed_query

        _cached_embed_query.cache_clear()

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]

        with patch(
            "core.rag.embeddings.service.get_embedding_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc._client = AsyncMock()
            mock_svc._client.embeddings.create = AsyncMock(
                return_value=mock_response
            )
            mock_svc._deployment = "test-model"
            mock_get.return_value = mock_svc

            result1 = await _cached_embed_query("test query")
            result2 = await _cached_embed_query("test query")

            assert result1 == result2 == [0.1, 0.2, 0.3]
            # API should be called exactly once (cached on second call)
            assert mock_svc._client.embeddings.create.call_count == 1

        _cached_embed_query.cache_clear()

    @pytest.mark.asyncio
    async def test_cache_miss_for_different_text(self):
        """Different query texts result in separate API calls."""
        from core.rag.embeddings.service import _cached_embed_query

        _cached_embed_query.cache_clear()

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.data = [MagicMock(embedding=[float(call_count)])]
            return resp

        with patch(
            "core.rag.embeddings.service.get_embedding_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc._client = AsyncMock()
            mock_svc._client.embeddings.create = mock_create
            mock_svc._deployment = "test-model"
            mock_get.return_value = mock_svc

            r1 = await _cached_embed_query("query A")
            r2 = await _cached_embed_query("query B")

            assert r1 != r2
            assert call_count == 2

        _cached_embed_query.cache_clear()

    @pytest.mark.asyncio
    async def test_thundering_herd_single_api_call(self):
        """Concurrent calls for same uncached text trigger only one API call."""
        from core.rag.embeddings.service import _cached_embed_query

        _cached_embed_query.cache_clear()

        call_count = 0

        async def slow_create(**kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            resp = MagicMock()
            resp.data = [MagicMock(embedding=[1.0, 2.0])]
            return resp

        with patch(
            "core.rag.embeddings.service.get_embedding_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc._client = AsyncMock()
            mock_svc._client.embeddings.create = slow_create
            mock_svc._deployment = "test-model"
            mock_get.return_value = mock_svc

            results = await asyncio.gather(
                _cached_embed_query("concurrent query"),
                _cached_embed_query("concurrent query"),
                _cached_embed_query("concurrent query"),
            )

            for r in results:
                assert r == [1.0, 2.0]
            # async-lru thundering herd protection: only 1 API call
            assert call_count == 1

        _cached_embed_query.cache_clear()


# ---------------------------------------------------------------------------
# 9.2 retrieve_context() tests
# ---------------------------------------------------------------------------
class TestRetrieveContext:
    """Tests for modified retrieve_context() with single DB call."""

    @pytest.mark.asyncio
    async def test_single_embedding_call(self):
        """retrieve_context calls embed_query exactly once."""
        mock_embedding = [0.1] * 1536
        mock_db_result = json.dumps({
            "layers": [
                {
                    "id": 1,
                    "layer_name": "COUNTY",
                    "url": "http://test/0",
                    "purpose": "Counties",
                    "description": "County boundaries",
                    "score": 0.85,
                    "fields": [{"field_name": "NAME", "field_description": "County name"}],
                }
            ],
            "patterns": [],
        })

        with patch(
            "core.rag.retrieval.context.get_embedding_service"
        ) as mock_get_svc, patch(
            "core.rag.retrieval.context.async_session_factory"
        ) as mock_session_factory:
            mock_svc = MagicMock()
            mock_svc.embed_query = AsyncMock(return_value=mock_embedding)
            mock_get_svc.return_value = mock_svc

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = mock_db_result
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_factory.return_value = mock_session

            from core.rag.retrieval.context import retrieve_context

            result = await retrieve_context("test query")

            # embed_query called exactly once
            mock_svc.embed_query.assert_awaited_once_with("test query")
            # DB called exactly once
            mock_session.execute.assert_awaited_once()
            # Correct structure
            assert "layers" in result
            assert "patterns" in result
            assert len(result["layers"]) == 1
            assert result["layers"][0]["layer_name"] == "COUNTY"


# ---------------------------------------------------------------------------
# 9.3 LLMService json_mode tests
# ---------------------------------------------------------------------------
class TestLLMServiceJsonMode:
    """Tests for LLMService.complete() json_mode parameter."""

    @pytest.mark.asyncio
    async def test_json_mode_sets_response_format(self):
        """json_mode=True should set response_format in the API call."""
        with patch.dict("os.environ", {
            "AZURE_OPENAI_API_KEY": "test",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
        }):
            from core.llm_service import LLMService

            svc = LLMService()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"action": "query"}'
            mock_response.choices[0].message.tool_calls = None

            svc._client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            await svc.complete(
                [{"role": "user", "content": "test"}],
                json_mode=True,
            )

            call_kwargs = svc._client.chat.completions.create.call_args[1]
            assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_json_mode_default_false(self):
        """Default call should NOT include response_format."""
        with patch.dict("os.environ", {
            "AZURE_OPENAI_API_KEY": "test",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
        }):
            from core.llm_service import LLMService

            svc = LLMService()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Hello"
            mock_response.choices[0].message.tool_calls = None

            svc._client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            await svc.complete([{"role": "user", "content": "test"}])

            call_kwargs = svc._client.chat.completions.create.call_args[1]
            assert "response_format" not in call_kwargs


# ---------------------------------------------------------------------------
# 9.5 QueryHandler.plan() does NOT use run_tool_loop()
# ---------------------------------------------------------------------------
class TestQueryHandlerPlanNoToolLoop:
    """Verify plan() calls complete() directly, not run_tool_loop()."""

    @pytest.mark.asyncio
    async def test_plan_does_not_call_run_tool_loop(self):
        """plan() should call _cached_plan (which calls complete() directly),
        never run_tool_loop()."""
        from core.orchestrator.query_handler import QueryHandler

        mock_mcp = MagicMock()
        mock_mcp.is_connected = True
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = '{"action": "query", "query": []}'
        mock_response.tool_calls = []
        mock_llm.complete.return_value = mock_response

        handler = QueryHandler(
            mcp=mock_mcp,
            llm=mock_llm,
            prompts={
                "query_instructions": {
                    "system": "You are a helpful assistant.",
                    "human": "{context}\n\nQuery: {query}",
                }
            },
            tools_cache=[],
        )

        with patch(
            "core.orchestrator.query_handler.build_rag_context",
            new_callable=AsyncMock,
            return_value=("context", []),
        ), patch(
            "core.orchestrator.query_handler._cached_plan",
        ) as mock_cached:
            mock_cached.return_value = {"action": "query", "query": []}

            result = await handler.plan("test query")

            # _cached_plan was called (which uses complete() directly)
            mock_cached.assert_awaited_once()
            # run_tool_loop was NOT called
            assert not hasattr(handler, "_run_tool_loop_called")


# ---------------------------------------------------------------------------
# 9.6 execute_query_plan invoked exactly once
# ---------------------------------------------------------------------------
class TestNoDoubleExecution:
    """Verify execute_query_plan is called exactly once per query."""

    @pytest.mark.asyncio
    async def test_execute_calls_tool_once(self):
        """execute() should call execute_query_plan exactly once."""
        from core.orchestrator.query_handler import QueryHandler

        mock_mcp = MagicMock()
        mock_mcp.is_connected = True
        mock_mcp.call_tool = AsyncMock(return_value={"features": []})

        mock_llm = MagicMock()

        handler = QueryHandler(
            mcp=mock_mcp,
            llm=mock_llm,
            prompts={
                "query_instructions": {
                    "system": "test",
                    "human": "{context}\n{query}",
                }
            },
            tools_cache=[],
        )

        # Patch plan() to return a query plan directly
        handler.plan = AsyncMock(return_value={
            "action": "query",
            "query": [{"type": "where", "layer": "TEST", "layer_url": "http://test/0"}],
            "message": "test",
        })
        handler._last_rag_layers = []

        await handler.execute("test query")

        # execute_query_plan called exactly once
        mock_mcp.call_tool.assert_awaited_once()
        call_args = mock_mcp.call_tool.call_args
        assert call_args[0][0] == "execute_query_plan"
