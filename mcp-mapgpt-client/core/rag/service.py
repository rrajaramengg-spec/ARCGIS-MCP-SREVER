"""Injectable RAG service — wraps retrieval and ingestion.

Thin delegation layer over existing RAG module functions. The value is
in the injectable interface (satisfies IRAGService protocol), not new logic.
"""

import logging
from typing import Any, Dict, List, Tuple

from core.rag.ingestion import ingest_layers as _ingest_layers
from core.rag.ingestion import ingest_query_patterns as _ingest_query_patterns
from core.rag.prompt import build_rag_context

logger = logging.getLogger(__name__)


class RAGService:
    """Injectable RAG service covering retrieval and ingestion.

    Delegates to existing module-level functions. Celery tasks continue
    using direct imports — they run in their own process with their own
    init_db() call.
    """

    async def build_context(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Retrieve RAG context for a query via semantic search.

        Args:
            query: Natural language query.

        Returns:
            Tuple of (formatted context string, raw layer dicts).
        """
        return await build_rag_context(query)

    async def ingest_layers(self, data: List[Dict[str, Any]]) -> Dict[str, int]:
        """Ingest layer definitions into the vector store.

        Args:
            data: List of layer definition dicts.

        Returns:
            Summary dict with counts (e.g. {"layers": N, "fields": M}).
        """
        return await _ingest_layers(data)

    async def ingest_query_patterns(
        self, data: List[Dict[str, Any]], replace: bool = False
    ) -> Dict[str, int]:
        """Ingest query pattern examples into the vector store.

        Args:
            data: List of query pattern dicts.
            replace: If True, replace existing patterns before ingesting.

        Returns:
            Summary dict with counts (e.g. {"patterns": N}).
        """
        return await _ingest_query_patterns(data, replace)
