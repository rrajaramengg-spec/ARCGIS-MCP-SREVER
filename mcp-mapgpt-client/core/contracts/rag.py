"""IRAGService protocol — behavioral contract for RAG retrieval and ingestion."""

from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class IRAGService(Protocol):
    """Protocol for RAG (Retrieval-Augmented Generation) services.

    Covers both retrieval (build_context) and ingestion (ingest_layers,
    ingest_query_patterns) — they share the same DB engine, session
    lifecycle, and embedding service.
    """

    async def build_context(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Retrieve RAG context for a query via semantic search.

        Args:
            query: Natural language query to find relevant layers/patterns.

        Returns:
            Tuple of (formatted context string, raw layer dicts).
        """
        ...

    async def ingest_layers(self, data: List[Dict[str, Any]]) -> Dict[str, int]:
        """Ingest layer definitions into the vector store.

        Args:
            data: List of layer definition dicts.

        Returns:
            Summary dict with counts (e.g. {"layers": N, "fields": M}).
        """
        ...

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
        ...
