"""
Embedding service using Azure OpenAI.
Generates vector embeddings via text-embedding-3-small.
Module-level @alru_cache ensures cache persistence across handler instances.
"""

import logging
from typing import List, Optional

import httpx
import openai
from async_lru import alru_cache

from core.config import ClientConfig

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

    def __init__(self, config: ClientConfig) -> None:
        self._client = openai.AsyncAzureOpenAI(
            api_key=config.azure_openai_api_key,
            azure_endpoint=config.azure_openai_endpoint,
            api_version=config.azure_openai_api_version,
            timeout=httpx.Timeout(30.0, connect=10.0),
            max_retries=2,
        )
        self._deployment = config.azure_openai_embedding_deployment
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


def get_embedding_service(config: Optional[ClientConfig] = None) -> EmbeddingService:
    """Get or create the embedding service singleton.

    Args:
        config: ClientConfig to use when creating the service for the first time.
            Ignored if the singleton already exists.
    """
    global _service
    if _service is None:
        if config is None:
            from core.config import settings

            config = settings
        _service = EmbeddingService(config)
    return _service
