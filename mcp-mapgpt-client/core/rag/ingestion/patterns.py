"""
Query pattern ingestion into kb_query_patterns.
"""

import json
import logging
from typing import Any, Dict, List

from sqlalchemy import delete

from ..database import KBQueryPattern, async_session_factory
from ..embeddings import get_embedding_service

logger = logging.getLogger(__name__)


async def ingest_query_patterns(
    data: List[Dict[str, Any]], replace: bool = False
) -> Dict[str, int]:
    """Ingest query pattern examples into kb_query_patterns.

    Args:
        data: Array of pattern objects with keys: prompt, query, operations.
        replace: If True, delete all existing patterns before inserting.

    Returns:
        Dict with count: {"patterns": N}.
    """
    embedding_service = get_embedding_service()
    count = 0

    async with async_session_factory() as db:
        if replace:
            await db.execute(delete(KBQueryPattern))
            logger.info("Cleared existing query patterns (replace=True)")

        # Collect prompts for batch embedding
        prompts = [item.get("prompt", "") for item in data if item.get("prompt")]
        if not prompts:
            return {"patterns": 0}

        embeddings = await embedding_service.embed_documents(prompts)

        embed_idx = 0
        for item in data:
            prompt = item.get("prompt", "")
            if not prompt:
                continue

            # Parse query_json: input has it as a JSON string or dict
            raw_query = item.get("query", "{}")
            if isinstance(raw_query, str):
                try:
                    query_json = json.loads(raw_query)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Skipping pattern with invalid query JSON string: %.80s",
                        raw_query,
                    )
                    continue
            elif isinstance(raw_query, dict):
                query_json = raw_query
            else:
                logger.warning(
                    "Skipping pattern with unsupported query type %s: %.80s",
                    type(raw_query).__name__,
                    str(raw_query),
                )
                continue

            operations = item.get("operations", [])

            pattern = KBQueryPattern(
                prompt=prompt,
                query_json=query_json,
                operations=operations,
                embedding=embeddings[embed_idx],
            )
            db.add(pattern)
            embed_idx += 1
            count += 1

        await db.commit()

    logger.info("Ingested %d query patterns", count)
    return {"patterns": count}
