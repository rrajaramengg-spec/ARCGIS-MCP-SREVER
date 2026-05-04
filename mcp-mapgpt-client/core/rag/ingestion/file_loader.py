"""
File-based ingestion dispatcher.
Reads JSON files and routes to the appropriate ingestion function.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from .layers import ingest_layers
from .patterns import ingest_query_patterns

logger = logging.getLogger(__name__)


async def ingest_from_file(file_path: str, doc_type: str) -> Dict[str, Any]:
    """Read a JSON file and dispatch to the appropriate ingestion function.

    Args:
        file_path: Path to the JSON file.
        doc_type: Either "layer" or "query_pattern".

    Returns:
        Result dict from the ingestion function.

    Raises:
        ValueError: If doc_type is not "layer" or "query_pattern".
        FileNotFoundError: If file_path does not exist.
    """
    valid_types = ("layer", "query_pattern")
    if doc_type not in valid_types:
        raise ValueError(
            f"Invalid doc_type '{doc_type}'. Must be one of: {', '.join(valid_types)}"
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    logger.info("Loaded %d items from %s (doc_type=%s)", len(data), file_path, doc_type)

    if doc_type == "layer":
        return await ingest_layers(data)
    else:
        return await ingest_query_patterns(data)
