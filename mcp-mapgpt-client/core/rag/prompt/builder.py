"""
RAG context builder — retrieval + formatting into a single context string.
"""

import logging
from typing import Any, Dict, List, Tuple

from ..retrieval import retrieve_context
from .formatting import format_layer_context, format_pattern_context

logger = logging.getLogger(__name__)


async def build_rag_context(query: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Retrieve context and format into structured prompt sections.

    Args:
        query: User query string.

    Returns:
        Tuple of (combined context string, raw layers list).
        The raw layers list is used for post-plan validation guardrails.
    """
    context = await retrieve_context(query)

    layer_section = format_layer_context(context["layers"])
    pattern_section = format_pattern_context(context["patterns"])

    combined = f"{layer_section}\n{pattern_section}"

    logger.info(
        "Built RAG context: %d layers, %d patterns, %d chars",
        len(context["layers"]),
        len(context["patterns"]),
        len(combined),
    )

    return combined, context["layers"]
