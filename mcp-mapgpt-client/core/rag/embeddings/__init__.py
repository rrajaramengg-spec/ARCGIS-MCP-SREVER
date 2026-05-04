"""
Embeddings sub-package — Azure OpenAI embedding service.
"""

from .service import EmbeddingService, get_embedding_service

__all__ = ["EmbeddingService", "get_embedding_service"]
