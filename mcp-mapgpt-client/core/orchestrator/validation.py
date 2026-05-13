"""
Plan validation and correction logic for the query handler.
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _sanitize_fields(fields: List[str]) -> List[str]:
    """Strip SQL aliases from field names before field-name guardrail.

    Examples:
        ["NAME AS county_name", "POP"]  →  ["NAME", "POP"]
        ["COUNT(*) AS total"]           →  ["COUNT(*)", "total"]  — kept as-is
    """
    if not fields:
        return fields
    clean: List[str] = []
    for f in fields:
        # Strip trailing " AS alias" (case-insensitive)
        base = re.split(r"\s+[Aa][Ss]\s+", f, maxsplit=1)[0].strip()
        if base:
            clean.append(base)
    return clean


def validate_plan(
    plan: Dict[str, Any],
    rag_layers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate and correct URLs and field names in a query plan.

    Compares every layer_url and fields entry against the known-good
    values from the RAG knowledge base.  Supports query, analyze, and
    locate-with-children actions.
    """
    action = plan.get("action")

    # Build lookup tables from RAG layers
    url_by_name: Dict[str, str] = {}
    fields_by_name: Dict[str, set] = {}
    known_urls: set = set()
    for layer in rag_layers:
        name = layer["layer_name"].upper()
        url = layer["url"]
        url_by_name[name] = url
        known_urls.add(url)
        fields_by_name[name] = {
            f["field_name"].upper()
            for f in layer.get("fields", [])
        }

    def _fix_node(node: Dict[str, Any]) -> None:
        # Auto-correct "tool" field → "join_type" (task 7.3)
        if "tool" in node and "join_type" not in node:
            logger.warning(
                "Plan guardrail: renamed 'tool' → 'join_type' (%s)",
                node["tool"],
            )
            node["join_type"] = node.pop("tool")

        layer_name = (node.get("layer") or "").upper()
        layer_url = node.get("layer_url", "")

        # URL guardrail
        if layer_url and layer_url not in known_urls:
            correct_url = url_by_name.get(layer_name)
            if correct_url:
                logger.warning(
                    "Plan guardrail: corrected URL for %s: %s → %s",
                    layer_name, layer_url, correct_url,
                )
                node["layer_url"] = correct_url
            else:
                logger.warning(
                    "Plan guardrail: unknown URL %s for layer %s — "
                    "no matching layer in KB",
                    layer_url, layer_name,
                )
        elif not layer_url and layer_name in url_by_name:
            node["layer_url"] = url_by_name[layer_name]
            logger.warning(
                "Plan guardrail: filled missing URL for %s", layer_name
            )

        # Field name guardrail
        plan_fields = node.get("fields")
        if plan_fields and layer_name in fields_by_name:
            plan_fields = _sanitize_fields(plan_fields)
            node["fields"] = plan_fields
            known = fields_by_name[layer_name]
            valid = [f for f in plan_fields if f.upper() in known]
            removed = set(f.upper() for f in plan_fields) - known
            if removed:
                logger.warning(
                    "Plan guardrail: removed unknown fields for %s: %s",
                    layer_name, removed,
                )
            node["fields"] = valid if valid else plan_fields

        # Recurse into children
        for child in node.get("children", []):
            _fix_node(child)

    if action == "query" and "query" in plan:
        for query_node in plan.get("query", []):
            _fix_node(query_node)
    elif action == "analyze" and "analyze" in plan:
        for analyze_node in plan.get("analyze", []):
            _fix_node(analyze_node)
    elif action == "locate":
        locate = plan.get("locate")
        nodes = locate if isinstance(locate, list) else [locate] if isinstance(locate, dict) else []
        for node in nodes:
            for child in node.get("children", []):
                _fix_node(child)

    return plan
