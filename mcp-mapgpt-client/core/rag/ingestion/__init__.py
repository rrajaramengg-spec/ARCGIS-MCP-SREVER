"""
Ingestion sub-package — write path for knowledge base tables.
"""

from .file_loader import ingest_from_file
from .layers import ingest_layers
from .patterns import ingest_query_patterns

__all__ = ["ingest_from_file", "ingest_layers", "ingest_query_patterns"]
