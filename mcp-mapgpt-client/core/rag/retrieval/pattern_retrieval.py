"""
Query pattern retrieval via cosine similarity on kb_query_patterns.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import select

from ..database import KBQueryPattern, async_session_factory
from ..embeddings import get_embedding_service

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5
_DEFAULT_MIN_SCORE = 0.5


async def retrieve_query_patterns(
    query: str, top_k: int = _DEFAULT_TOP_K, min_score: float = _DEFAULT_MIN_SCORE
) -> List[Dict[str, Any]]:
    """Retrieve query patterns by cosine similarity on prompt embedding.

    Args:
        query: User query string.
        top_k: Maximum number of patterns to return.
        min_score: Minimum similarity score threshold.

    Returns:
        List of pattern dicts with prompt, query_json, operations, score.
    """
    embedding_service = get_embedding_service()
    query_embedding = await embedding_service.embed_query(query)

    async with async_session_factory() as db:
        stmt = select(
            KBQueryPattern.prompt,
            KBQueryPattern.query_json,
            KBQueryPattern.operations,
            KBQueryPattern.embedding.cosine_distance(query_embedding).label("distance"),
        ).order_by("distance").limit(top_k)

        result = await db.execute(stmt)
        rows = result.all()

    patterns: List[Dict[str, Any]] = []
    for row in rows:
        score = 1 - (row.distance / 2)
        if score >= min_score:
            patterns.append({
                "prompt": row.prompt,
                "query_json": row.query_json,
                "operations": row.operations,
                "score": score,
            })

    logger.debug("Retrieved %d patterns (min_score=%.2f)", len(patterns), min_score)
    return patterns
