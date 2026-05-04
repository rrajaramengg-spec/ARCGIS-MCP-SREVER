"""
Embedding service using Azure OpenAI.
Generates vector embeddings via text-embedding-3-small.
Module-level @alru_cache ensures cache persistence across handler instances.
"""

import logging
import os
from typing import List

import openai
from async_lru import alru_cache

logger = logging.getLogger(__name__)


# Module-level cached embedding function.
# NOT an instance method — @alru_cache on self.method uses `self` as cache key,
# defeating caching across handler/service instances.
@alru_cache(maxsize=256, ttl=3600)
async def _cached_embed_query(text: str) -> List[float]:
    """Generate embedding for a single query text, with LRU caching.

    Cache key is the text string only. Uses the module-level singleton client.
    """
    service = get_embedding_service()
    response = await service._client.embeddings.create(
        input=[text],
        model=service._deployment,
    )
    return response.data[0].embedding


class EmbeddingService:
    """Service for generating embeddings using Azure OpenAI directly."""

    def __init__(self) -> None:
        self._client = openai.AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        )
        self._deployment = os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
        )
        logger.info("EmbeddingService initialised — deployment=%s", self._deployment)
        logger.info(
            "Embedding cache: maxsize=256, ttl=3600, info=%s",
            _cached_embed_query.cache_info(),
        )

    async def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query text (cached via module-level LRU)."""
        if not text:
            raise ValueError("Text cannot be empty")
        return await _cached_embed_query(text)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents in a single batch.

        Bypasses the cache — batch embedding always invokes the API directly.
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")

        response = await self._client.embeddings.create(
            input=texts,
            model=self._deployment,
        )
        logger.info("Generated embeddings for %d documents", len(texts))
        return [item.embedding for item in response.data]


# Module-level singleton
_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the embedding service singleton."""
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
