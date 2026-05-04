"""
Layer and field ingestion into kb_layers + kb_fields.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import KBField, KBLayer, async_session_factory
from ..embeddings import get_embedding_service

logger = logging.getLogger(__name__)


async def ingest_layers(data: List[Dict[str, Any]]) -> Dict[str, int]:
    """Ingest layer definitions with fields into kb_layers and kb_fields.

    Args:
        data: Array of layer objects with keys: layer, url, purpose, description, fields.

    Returns:
        Dict with counts: {"layers": N, "fields": M}.
    """
    embedding_service = get_embedding_service()
    layers_count = 0
    fields_count = 0

    async with async_session_factory() as db:
        for item in data:
            layer_name = item.get("layer")
            if not layer_name:
                logger.warning("Skipping layer object with no 'layer' key")
                continue

            url = item.get("url", "")
            purpose = item.get("purpose", "")
            description = item.get("description", "")

            # Embed composite text for layer
            composite = f"{layer_name}: {purpose}. {description}"
            layer_embedding = await embedding_service.embed_query(composite)

            # Upsert layer
            layer = await _upsert_layer(
                db, layer_name, url, purpose, description, layer_embedding
            )
            layers_count += 1

            # Process fields
            input_fields = item.get("fields", [])
            existing_field_names = set()

            for field_obj in input_fields:
                field_name = field_obj.get("name", "")
                field_desc = field_obj.get("description", "")
                if not field_name:
                    continue

                field_text = f"{field_name}: {field_desc}"
                field_embedding = await embedding_service.embed_query(field_text)

                await _upsert_field(
                    db, layer.id, field_name, field_desc, field_embedding
                )
                existing_field_names.add(field_name)
                fields_count += 1

            # Remove fields no longer in the input
            await _remove_stale_fields(db, layer.id, existing_field_names)

        await db.commit()

    logger.info("Ingested %d layers, %d fields", layers_count, fields_count)
    return {"layers": layers_count, "fields": fields_count}


async def _upsert_layer(
    db: AsyncSession,
    layer_name: str,
    url: str,
    purpose: str,
    description: str,
    embedding: List[float],
) -> KBLayer:
    """Insert or update a layer row."""
    stmt = select(KBLayer).where(KBLayer.layer_name == layer_name)
    result = await db.execute(stmt)
    layer = result.scalar_one_or_none()

    if layer:
        layer.url = url
        layer.purpose = purpose
        layer.description = description
        layer.embedding = embedding
    else:
        layer = KBLayer(
            layer_name=layer_name,
            url=url,
            purpose=purpose,
            description=description,
            embedding=embedding,
        )
        db.add(layer)
        await db.flush()

    return layer


async def _upsert_field(
    db: AsyncSession,
    layer_id: int,
    field_name: str,
    field_description: str,
    embedding: List[float],
) -> KBField:
    """Insert or update a field row."""
    stmt = select(KBField).where(
        KBField.layer_id == layer_id, KBField.field_name == field_name
    )
    result = await db.execute(stmt)
    field = result.scalar_one_or_none()

    if field:
        field.field_description = field_description
        field.embedding = embedding
    else:
        field = KBField(
            layer_id=layer_id,
            field_name=field_name,
            field_description=field_description,
            embedding=embedding,
        )
        db.add(field)
        await db.flush()

    return field


async def _remove_stale_fields(
    db: AsyncSession, layer_id: int, current_names: set
) -> None:
    """Delete fields that are no longer in the input set."""
    stmt = select(KBField).where(KBField.layer_id == layer_id)
    result = await db.execute(stmt)
    existing = result.scalars().all()

    for field in existing:
        if field.field_name not in current_names:
            await db.delete(field)
            logger.debug("Removed stale field: %s", field.field_name)
