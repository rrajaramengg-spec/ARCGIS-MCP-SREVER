"""
RAG module — internal pipeline infrastructure.
Exposes async functions for knowledge base ingestion, retrieval, and context building.
Each function manages its own AsyncSession via async_session_factory.
"""

from .database import async_session_factory, close_db, init_db
from .ingestion import ingest_from_file, ingest_layers, ingest_query_patterns
from .prompt import build_rag_context
from .retrieval import retrieve_context

__all__ = [
    "async_session_factory",
    "build_rag_context",
    "close_db",
    "ingest_from_file",
    "ingest_layers",
    "ingest_query_patterns",
    "init_db",
    "retrieve_context",
]
