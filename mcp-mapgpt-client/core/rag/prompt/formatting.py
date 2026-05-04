"""
Context formatting functions for structured RAG output.
Converts retrieval results into prompt-ready text sections.
"""

import json
from typing import Any, Dict, List


def format_layer_context(layers: List[Dict[str, Any]]) -> str:
    """Format matched layers into a structured text block for LLM context.

    Args:
        layers: List of layer dicts with layer_name, url, purpose, fields.

    Returns:
        Formatted string with === AVAILABLE LAYERS === header.
    """
    lines = ["=== AVAILABLE LAYERS ==="]

    if not layers:
        lines.append("No matching layers found.")
        return "\n".join(lines)

    for layer in layers:
        lines.append(f"Layer: {layer['layer_name'].upper()}")
        lines.append(f"URL: {layer['url']}")
        lines.append(f"Purpose: {layer['purpose']}")

        fields = layer.get("fields", [])
        if fields:
            lines.append("Fields:")
            for field in fields:
                lines.append(
                    f"  - {field['field_name']}: {field['field_description']}"
                )

        lines.append("")  # blank line between layers

    return "\n".join(lines)


def format_pattern_context(patterns: List[Dict[str, Any]]) -> str:
    """Format matched query patterns into a structured text block for LLM context.

    Args:
        patterns: List of pattern dicts with prompt, query_json.

    Returns:
        Formatted string with === QUERY PATTERN EXAMPLES === header.
    """
    lines = ["=== QUERY PATTERN EXAMPLES ==="]

    if not patterns:
        lines.append("No matching query patterns found.")
        return "\n".join(lines)

    for pattern in patterns:
        lines.append(f"Q: {pattern['prompt']}")

        query_json = pattern["query_json"]
        if isinstance(query_json, dict):
            lines.append(f"A: {json.dumps(query_json, separators=(',', ':'))}")
        else:
            lines.append(f"A: {query_json}")

        lines.append("")  # blank line between patterns

    return "\n".join(lines)
