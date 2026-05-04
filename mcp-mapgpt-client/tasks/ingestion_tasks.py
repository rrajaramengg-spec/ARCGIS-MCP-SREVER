"""
Background tasks for document ingestion.
Migrated from app/tasks/ingestion_tasks.py.
"""

import asyncio
import logging
from typing import Any, Dict

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ingest_file_task", bind=True)
def ingest_file_task(
    self, file_path: str, doc_type: str, metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Background task for file ingestion."""

    async def _async_ingest():
        from core.rag.database import init_db
        from core.rag.ingestion import ingest_from_file

        init_db()
        result = await ingest_from_file(file_path, doc_type)
        return result

    try:
        result = asyncio.run(_async_ingest())
        logger.info("File ingestion completed: %s", result)
        return result
    except Exception as e:
        logger.error("File ingestion failed: %s", e)
        raise


@celery_app.task(name="ingest_api_docs_task", bind=True)
def ingest_api_docs_task(self, api_docs: list) -> Dict[str, Any]:
    """Background task for API documentation ingestion."""

    async def _async_ingest():
        from core.rag.database import init_db
        from core.rag.ingestion import ingest_layers

        init_db()
        result = await ingest_layers(api_docs)
        return result

    try:
        result = asyncio.run(_async_ingest())
        logger.info("API docs ingestion completed: %s", result)
        return result
    except Exception as e:
        logger.error("API docs ingestion failed: %s", e)
        raise
