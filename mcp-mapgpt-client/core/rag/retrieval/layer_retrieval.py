"""
Layer retrieval with hybrid scoring and field enrichment via FK join.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy import select

from ..database import KBField, KBLayer, async_session_factory
from ..embeddings import get_embedding_service

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 10
_DEFAULT_MIN_SCORE = 0.3
_ALPHA = 0.7  # weight for cosine similarity vs keyword matching


async def retrieve_layers(
    query: str, top_k: int = _DEFAULT_TOP_K, min_score: float = _DEFAULT_MIN_SCORE
) -> List[Dict[str, Any]]:
    """Retrieve layers using hybrid scoring (cosine + keyword on layer_name/purpose).

    Args:
        query: User query string.
        top_k: Maximum number of layers to return.
        min_score: Minimum combined score threshold.

    Returns:
        List of layer dicts with id, layer_name, url, purpose, description, score.
    """
    embedding_service = get_embedding_service()
    query_embedding = await embedding_service.embed_query(query)
    keywords = query.lower().split()

    async with async_session_factory() as db:
        # Fetch more candidates than needed for hybrid re-ranking
        stmt = select(
            KBLayer.id,
            KBLayer.layer_name,
            KBLayer.url,
            KBLayer.purpose,
            KBLayer.description,
            KBLayer.embedding.cosine_distance(query_embedding).label("distance"),
        ).order_by("distance").limit(top_k * 2)

        result = await db.execute(stmt)
        rows = result.all()

    layers: List[Dict[str, Any]] = []
    for row in rows:
        cosine_score = 1 - (row.distance / 2)

        # Keyword matching on layer_name and purpose
        searchable = f"{row.layer_name} {row.purpose}".lower()
        keyword_matches = sum(1 for kw in keywords if kw in searchable)
        keyword_score = (
            min(keyword_matches / len(keywords), 1.0) if keywords else 0
        )

        combined = (_ALPHA * cosine_score) + ((1 - _ALPHA) * keyword_score)

        if combined >= min_score:
            layers.append({
                "id": row.id,
                "layer_name": row.layer_name,
                "url": row.url,
                "purpose": row.purpose,
                "description": row.description,
                "score": combined,
            })

    layers.sort(key=lambda x: x["score"], reverse=True)
    return layers[:top_k]


async def get_fields_for_layers(
    layer_ids: List[int],
) -> Dict[int, List[Dict[str, str]]]:
    """Fetch all fields for the given layer IDs, grouped by layer_id.

    Args:
        layer_ids: List of kb_layers.id values.

    Returns:
        Dict mapping layer_id to list of {"field_name": ..., "field_description": ...}.
    """
    if not layer_ids:
        return {}

    async with async_session_factory() as db:
        stmt = (
            select(KBField.layer_id, KBField.field_name, KBField.field_description)
            .where(KBField.layer_id.in_(layer_ids))
            .order_by(KBField.layer_id, KBField.field_name)
        )
        result = await db.execute(stmt)
        rows = result.all()

    grouped: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.layer_id].append({
            "field_name": row.field_name,
            "field_description": row.field_description,
        })

    return dict(grouped)
