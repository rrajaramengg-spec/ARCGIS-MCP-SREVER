"""
Combined retrieval using rag_unified_search() stored function.
Single embedding call + single DB round-trip for the full RAG pipeline.
"""

import json
import logging
import time
from typing import Any, Dict, List

from sqlalchemy import text

from ..database import async_session_factory
from ..embeddings import get_embedding_service

logger = logging.getLogger(__name__)


async def retrieve_context(query: str) -> Dict[str, List[Dict[str, Any]]]:
    """Execute the full retrieval pipeline via the rag_unified_search() stored function.

    Single embedding call + single DB round-trip for the full RAG pipeline, 
    returning both layers and patterns in a single result.

    Args:
        query: User query string.

    Returns:
        {"layers": [...], "patterns": [...]} where each layer includes its fields.
    """
    start = time.time()

    # Single embedding call (cached via module-level @alru_cache)
    embedding_service = get_embedding_service()
    try:
        query_embedding = await embedding_service.embed_query(query)
    except Exception as e:
        logger.error("Embedding failed for query, returning empty context: %s", e)
        return {"layers": [], "patterns": []}

    # Single DB call via stored function
    async with async_session_factory() as db:
        result = await db.execute(
            text("SELECT rag_unified_search(:embedding, :query_text)"),
            {
                "embedding": str(query_embedding),
                "query_text": query,
            },
        )
        row = result.scalar()

    # Parse JSONB result
    if isinstance(row, str):
        parsed = json.loads(row)
    elif isinstance(row, dict):
        parsed = row
    else:
        parsed = {"layers": [], "patterns": []}

    layers = parsed.get("layers", [])
    patterns = parsed.get("patterns", [])

    elapsed_ms = (time.time() - start) * 1000
    logger.info(
        "retrieve_context: %d layers, %d patterns (%.0f ms)",
        len(layers),
        len(patterns),
        elapsed_ms,
    )

    return {"layers": layers, "patterns": patterns}
