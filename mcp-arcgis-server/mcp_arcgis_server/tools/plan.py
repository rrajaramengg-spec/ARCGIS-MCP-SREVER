"""
Query plan execution tool for ArcGIS feature layers.

Tools: execute_query_plan
"""

import asyncio
import json
import logging
import time
from typing import Annotated, Any, Dict, List

from pydantic import Field

from ..arcgis.client import ArcGISClient
from ..arcgis.geometry import union_feature_geometries
from ._registry import register_tool

logger = logging.getLogger(__name__)


def _sanitize_fields(fields: List[str]) -> List[str]:
    """Strip SQL aliases (e.g. 'FIELD as alias') from field names."""
    clean = []
    for f in fields:
        name = f.split(" as ", 1)[0].split(" AS ", 1)[0].strip()
        if name:
            clean.append(name)
    return clean


@register_tool(
    name="execute_query_plan",
    description=(
        "Execute a full query plan in a single call. Accepts the JSON query plan "
        "produced by the RAG+LLM planning step. Supports single-layer WHERE and COUNT "
        "queries. For parent-child spatial join plans, automatically unions ALL parent "
        "feature geometries into a single polygon before using it as a spatial filter "
        "on child layers — no separate union step needed. Returns aggregated results "
        "with parent features and child query results."
    ),
)
async def execute_query_plan(
    client: ArcGISClient,
    query_plan: Annotated[str, Field(description=(
        "JSON string of the full query plan as produced by RAG+LLM planning. "
        'Format: {"action": "query", "query": [{"type": "where|count", "layer": "NAME", '
        '"layer_url": "https://...", "where": "SQL", "fields": ["F1"], '
        '"children": [...]}]}'
    ))],
) -> Dict[str, Any]:
    """Execute a full query plan in a single call.

    Accepts the JSON query plan produced by the RAG+LLM planning step and executes
    all operations (single-layer query, count, parent-child spatial joins).
    """
    try:
        plan = json.loads(query_plan)
    except (json.JSONDecodeError, TypeError) as exc:
        return {"error": "Invalid query plan JSON", "detail": str(exc)}

    queries = plan.get("query")
    if not queries or not isinstance(queries, list):
        return {
            "error": "Unsupported query plan structure",
            "detail": "Expected 'query' array in plan",
        }

    results: List[Dict[str, Any]] = []

    for q in queries:
        layer_url = q.get("layer_url")
        if not layer_url:
            results.append({
                "error": "Missing layer_url",
                "detail": f"Layer '{q.get('layer', 'unknown')}' has no layer_url",
            })
            continue

        query_type = q.get("type", "where")
        where = q.get("where", "1=1")
        fields = _sanitize_fields(q.get("fields", []))
        out_fields = ",".join(fields) if fields else "*"
        children = q.get("children", [])

        try:
            if query_type == "count" and not children:
                parent_result = await client.query_layer(
                    layer_url=layer_url, where=where, return_count_only=True,
                )
                results.append({
                    "layer": q.get("layer"), "layer_url": layer_url,
                    "type": "count", "count": parent_result.get("count", 0),
                })
            elif not children:
                parent_result = await client.query_layer(
                    layer_url=layer_url, where=where,
                    out_fields=out_fields, return_geometry=True,
                )
                results.append({
                    "layer": q.get("layer"), "layer_url": layer_url,
                    "type": "where", **parent_result,
                })
            else:
                parent_start = time.perf_counter()
                parent_result = await client.query_layer(
                    layer_url=layer_url, where=where,
                    out_fields=out_fields, return_geometry=True,
                )
                parent_features = parent_result.get("features", [])
                if not parent_features:
                    results.append({
                        "layer": q.get("layer"),
                        "error": "No parent features found", "where": where,
                    })
                    continue

                parent_geometry = None
                union_start = time.perf_counter()
                try:
                    parent_geometry = union_feature_geometries(parent_features)
                except Exception as union_exc:
                    logger.error(
                        "Geometry union failed for layer %s (%d features): %s",
                        q.get("layer"), len(parent_features), union_exc,
                        exc_info=True,
                    )
                    results.append({
                        "layer": q.get("layer"),
                        "error": "Geometry union failed",
                        "detail": str(union_exc) or "Could not union parent geometries",
                    })
                    continue
                union_ms = (time.perf_counter() - union_start) * 1000

                if not parent_geometry:
                    results.append({
                        "layer": q.get("layer"),
                        "error": "Parent features have no geometry",
                    })
                    continue

                # Execute child queries in parallel via asyncio.gather
                async def _execute_child_query(
                    child: Dict[str, Any],
                    parent_geom: Dict[str, Any],
                ) -> Dict[str, Any]:
                    """Execute a single child query with timing."""
                    child_start = time.perf_counter()
                    child_url = child.get("layer_url")
                    if not child_url:
                        return {
                            "error": "Missing layer_url",
                            "detail": f"Child layer '{child.get('layer', 'unknown')}' has no layer_url",
                        }

                    child_type = child.get("type", "where")
                    child_where = child.get("where", "1=1")
                    child_fields = _sanitize_fields(child.get("fields", []))
                    child_out_fields = ",".join(child_fields) if child_fields else "*"

                    if child_type == "count":
                        child_result = await client.query_layer(
                            layer_url=child_url, where=child_where,
                            return_count_only=True,
                            geometry=parent_geom,
                            spatial_rel="esriSpatialRelIntersects",
                        )
                        execution_ms = (time.perf_counter() - child_start) * 1000
                        return {
                            "layer": child.get("layer"), "layer_url": child_url,
                            "type": "count", "alias": child.get("alias"),
                            "count": child_result.get("count", 0),
                            "execution_ms": round(execution_ms, 2),
                        }
                    else:
                        child_result = await client.spatial_query(
                            layer_url=child_url, geometry=parent_geom,
                            where=child_where, out_fields=child_out_fields,
                            spatial_rel="esriSpatialRelIntersects",
                        )
                        execution_ms = (time.perf_counter() - child_start) * 1000
                        return {
                            "layer": child.get("layer"), "layer_url": child_url,
                            "type": "where", "alias": child.get("alias"),
                            "execution_ms": round(execution_ms, 2),
                            **child_result,
                        }

                children_start = time.perf_counter()
                child_tasks = [
                    _execute_child_query(child, parent_geometry)
                    for child in children
                ]
                child_raw_results = await asyncio.gather(
                    *child_tasks, return_exceptions=True
                )
                children_ms = (time.perf_counter() - children_start) * 1000

                # Convert exceptions to error dicts
                child_results: List[Dict[str, Any]] = []
                for i, cr in enumerate(child_raw_results):
                    if isinstance(cr, Exception):
                        logger.error(
                            "Child query %d failed: %s",
                            i, cr, exc_info=cr,
                        )
                        child_results.append({
                            "layer": children[i].get("layer"),
                            "error": "Child query failed",
                            "detail": str(cr) or type(cr).__name__,
                        })
                    else:
                        child_results.append(cr)

                logger.info(
                    "Spatial join %s: parent_ms=%.0f, union_ms=%.0f, children_ms=%.0f (%d children)",
                    q.get("layer"),
                    (time.perf_counter() - parent_start) * 1000 - union_ms - children_ms,
                    union_ms,
                    children_ms,
                    len(children),
                )

                results.append({
                    "layer": q.get("layer"), "layer_url": layer_url,
                    "type": "spatial_join",
                    "parent": parent_result, "children": child_results,
                })

        except Exception as exc:
            logger.error(
                "execute_query_plan error for layer %s: %s",
                q.get("layer"), exc, exc_info=True,
            )
            results.append({
                "layer": q.get("layer"),
                "error": "Execution failed", "detail": str(exc),
            })

    if len(results) == 1:
        return results[0]

    return {"results": results, "count": len(results)}
