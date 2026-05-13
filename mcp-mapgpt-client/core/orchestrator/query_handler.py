"""
QueryHandler - RAG + LLM planning, validation, and graph-based execution.

All executable actions (query, analyze, locate) go through the DAG-based
graph runtime.  Non-executable actions (message, route) return directly.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.config import ClientConfig
from core.llm_service import LLMService
from core.mcp_client import MCPClient
from core.rag import build_rag_context
from core.history import ConversationHistory
from core.response_cache import ResponseCache

from .base import BaseHandler, extract_json, register_handler
from .validation import validate_plan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level utilities (moved from utils.py)
# ---------------------------------------------------------------------------

from async_lru import alru_cache

_llm_registry: Dict[int, Any] = {}


def _register_llm(llm: LLMService) -> None:
    """Register an LLM service instance for the cached plan function."""
    _llm_registry[id(llm)] = llm


def _normalize_query(query: str) -> str:
    """Normalize query for cache key: lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", query.strip().lower())


def _hash_context(context_str: str) -> str:
    """Hash RAG context string for cache key."""
    return hashlib.md5(context_str.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Response result helpers
# ---------------------------------------------------------------------------


def _decompose_proximity(raw: Dict[str, Any], node: Any) -> List[Dict[str, Any]]:
    """Split find_nearby compound blob into 3 feature_set results.

    Args:
        raw: Raw compound result from the find_nearby MCP tool.
        node: The graph node that produced this artifact.

    Returns:
        List of 3 feature_set dicts with roles: buffer, distance_line, result.
    """
    sr = raw.get("spatialReference", {"wkid": 4326})
    return [
        {
            "type": "feature_set",
            "layer": "_buffer",
            "features": [{"geometry": raw["buffer_geometry"]}],
            "count": 1,
            "geometryType": "esriGeometryPolygon",
            "spatialReference": sr,
            "fields": [],
            "role": "buffer",
        },
        {
            "type": "feature_set",
            "layer": "_distance",
            "features": raw.get("proximity_lines", []),
            "count": len(raw.get("proximity_lines", [])),
            "geometryType": "esriGeometryPolyline",
            "spatialReference": sr,
            "fields": [],
            "role": "distance_line",
        },
        {
            "type": "feature_set",
            "layer": getattr(node, "layer_url", "") or "",
            "features": raw.get("near_features", []),
            "count": raw.get("count", 0),
            "geometryType": raw.get("geometryType", "esriGeometryPoint"),
            "spatialReference": sr,
            "fields": raw.get("fields", []),
            "role": "result",
        },
    ]


def _artifact_to_result(
    raw: Dict[str, Any], meta: Any, node: Any,
) -> Dict[str, Any]:
    """Convert a single graph artifact into a typed result dict.

    Args:
        raw: Raw artifact data dict.
        meta: ArtifactMeta with producer info and artifact_type.
        node: The graph node that produced this artifact.

    Returns:
        A typed result dict with ``type`` and ``role`` fields.
    """
    from core.orchestrator.graph.context import ArtifactType

    at = meta.artifact_type

    # Geocode → geocode type
    if at == ArtifactType.GEOMETRY:
        candidates = raw.get("candidates", [])
        best = candidates[0] if candidates else {}
        return {
            "type": "geocode",
            "location": best.get("location", raw),
            "address": best.get("address", ""),
            "score": best.get("score", 0),
            "candidates": candidates,
        }

    # Buffer zone → feature_set with buffer role
    if at == ArtifactType.BUFFER_ZONE:
        return {
            "type": "feature_set",
            "layer": "_buffer",
            "features": [{"geometry": raw}] if raw else [],
            "count": 1 if raw else 0,
            "geometryType": "esriGeometryPolygon",
            "spatialReference": raw.get("spatialReference", {"wkid": 4326}),
            "fields": [],
            "role": "buffer",
        }

    # Count → feature_set with empty features
    if at == ArtifactType.COUNT:
        return {
            "type": "feature_set",
            "layer": getattr(node, "layer_url", "") or "",
            "features": [],
            "count": raw.get("count", 0),
            "geometryType": None,
            "spatialReference": None,
            "fields": [],
            "role": "result",
        }

    # Summary → feature_set with stat attributes as features
    if at == ArtifactType.SUMMARY:
        stats = raw.get("statistics", {})
        field_name = raw.get("field", raw.get("field_name", ""))
        if stats:
            # Numeric summary → single-row
            features = [{"attributes": {**stats, "null_count": raw.get("null_count", 0)}}]
            fields = [{"name": k, "type": "esriFieldTypeDouble"} for k in stats]
        else:
            # String summary → multi-row unique values
            uv = raw.get("unique_values", [])
            features = [{"attributes": {"value": v.get("value"), "count": v.get("count", 0)}} for v in uv]
            fields = [
                {"name": "value", "type": "esriFieldTypeString"},
                {"name": "count", "type": "esriFieldTypeInteger"},
            ]
        return {
            "type": "feature_set",
            "layer": field_name,
            "features": features,
            "count": len(features),
            "geometryType": None,
            "spatialReference": None,
            "fields": fields,
            "role": "result",
        }

    # Union geometry — intermediate, but include as source marker
    if at == ArtifactType.UNION_GEOMETRY:
        return {
            "type": "feature_set",
            "layer": "_union",
            "features": [{"geometry": raw}] if raw else [],
            "count": 1 if raw else 0,
            "geometryType": "esriGeometryPolygon",
            "spatialReference": raw.get("spatialReference", {"wkid": 4326}) if isinstance(raw, dict) else {"wkid": 4326},
            "fields": [],
            "role": "source",
        }

    # Default: FEATURE_SET → feature_set with result role
    return {
        "type": "feature_set",
        "layer": getattr(node, "layer_url", "") or "",
        "features": raw.get("features", []),
        "count": raw.get("count", len(raw.get("features", []))),
        "geometryType": raw.get("geometryType", None),
        "spatialReference": raw.get("spatialReference", None),
        "fields": raw.get("fields", []),
        "role": "result",
    }


@alru_cache(maxsize=128, ttl=300)
async def _cached_plan(
    normalized_query: str,
    context_hash: str,
    system_prompt: str,
    human_message: str,
    llm_service_id: int,
) -> Dict[str, Any]:
    """Module-level cached plan generation."""
    llm = _llm_registry.get(llm_service_id)
    if llm is None:
        raise RuntimeError("LLM service not registered for cached plan call")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": human_message},
    ]
    response = await llm.complete(messages, tools=None, json_mode=True)

    if response.content:
        try:
            result = extract_json(response.content)
            result.setdefault("action", "message")
            return result
        except json.JSONDecodeError:
            return {"action": "message", "message": response.content}
    return {"action": "message", "message": "No response generated."}


@register_handler("query")
class QueryHandler(BaseHandler):
    """Handles the full query pipeline: RAG -> LLM -> validate -> execute."""

    def __init__(
        self,
        mcp: MCPClient,
        llm: LLMService,
        prompts: Dict[str, Any],
        tools_cache: List[Dict[str, Any]],
        rag_service=None,
        graph_runtime=None,
        config: Optional[ClientConfig] = None,
    ) -> None:
        super().__init__(mcp, llm)
        self._prompts = prompts
        self._tools_cache = tools_cache
        self._rag_service = rag_service
        self._last_rag_layers: List[Dict[str, Any]] = []
        self._progress_callback: Optional[Callable] = None
        self._graph_runtime = graph_runtime
        self._config = config
        _register_llm(llm)

    def _resolve_layer_name(self, layer_url: str) -> Optional[str]:
        """Resolve human-readable layer name from RAG metadata.

        Args:
            layer_url: Full ArcGIS REST URL of the layer.

        Returns:
            Human-readable layer name if found, None otherwise.
        """
        if not self._last_rag_layers or not layer_url:
            return None
        for rag_layer in self._last_rag_layers:
            if rag_layer.get("url") == layer_url:
                return rag_layer.get("layer_name")
        return None

    def _build_node_label(self, node: Any) -> str:
        """Build a human-readable label for a graph node.

        Args:
            node: A typed graph node instance.

        Returns:
            Descriptive label string for DAG visualization.
        """
        nt = node.node_type
        if nt == "geocode":
            addr = getattr(node, "address", "")
            return f"Geocode '{addr}'" if addr else "Geocode"
        layer_url = getattr(node, "layer_url", "") or ""
        layer_name = self._resolve_layer_name(layer_url)
        if not layer_name and layer_url:
            # Fallback: extract last meaningful segment from URL
            parts = layer_url.rstrip("/").split("/")
            # Skip numeric layer IDs (e.g., /0, /1)
            for part in reversed(parts):
                if not part.isdigit():
                    layer_name = part
                    break
        if nt == "query":
            return f"Query {layer_name}" if layer_name else "Query"
        if nt == "buffer":
            dist = getattr(node, "distance", "")
            unit = getattr(node, "unit", "")
            return f"Buffer {dist}{unit}"
        if nt == "proximity":
            return f"Find Nearby {layer_name}" if layer_name else "Find Nearby"
        if nt == "union":
            return "Union"
        if nt == "spatial_join":
            return f"Spatial Join {layer_name}" if layer_name else "Spatial Join"
        if nt == "summarize":
            return "Summarize"
        if nt == "count":
            return f"Count {layer_name}" if layer_name else "Count"
        return node.node_id

    async def _get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get MCP tools formatted for OpenAI (cached)."""
        if not self._tools_cache:
            mcp_tools = await self._mcp.list_tools()
            self._tools_cache.extend(LLMService.mcp_tools_to_openai_format(mcp_tools))
            logger.info("Loaded %d MCP tools for LLM", len(self._tools_cache))
        return self._tools_cache

    # -- Planning ----------------------------------------------------------

    async def plan(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a query plan via RAG + LLM without executing against ArcGIS."""
        overall_start = time.perf_counter()
        logger.info("Planning query: %s", query[:100])

        rag_start = time.perf_counter()
        if self._rag_service is not None:
            context_str, rag_layers = await self._rag_service.build_context(query)
        else:
            context_str, rag_layers = await build_rag_context(query)
        self._last_rag_layers = rag_layers
        rag_ms = (time.perf_counter() - rag_start) * 1000
        logger.info("RAG context built (%.0f ms)", rag_ms)

        # Guard: if RAG returns no layers and no patterns, don't call LLM
        if not rag_layers and not context_str.strip():
            logger.warning("RAG returned empty context for query: %s", query[:100])
            return self.build_response(
                action="message",
                message="No relevant layers or patterns found in the knowledge base for this query. Please ingest layer data first.",
                data=None,
            )

        result = await self._plan_from_context(
            query, context_str, session_id=session_id
        )

        total_ms = (time.perf_counter() - overall_start) * 1000
        logger.info("Plan pipeline complete (%.0f ms total)", total_ms)
        return result

    async def _plan_from_context(
        self,
        query: str,
        context_str: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a plan from pre-computed RAG context."""
        system_prompt = self._prompts["query_instructions"]["system"]
        human_template = self._prompts["query_instructions"]["human"]
        human_message = human_template.format(context=context_str, query=query)

        history_turns: List[Dict[str, Any]] = []
        if session_id:
            try:
                history_turns = await ConversationHistory.get_turns(session_id)
            except Exception as exc:
                logger.warning("History retrieval failed, proceeding without: %s", exc)

        norm_query = _normalize_query(query)
        ctx_hash = _hash_context(context_str)

        if history_turns:
            return await self._plan_with_history(
                system_prompt, human_message, history_turns
            )
        return await _cached_plan(
            norm_query, ctx_hash, system_prompt, human_message, id(self._llm)
        )

    async def _plan_with_history(
        self,
        system_prompt: str,
        human_message: str,
        history_turns: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a plan with conversation history injected."""
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        messages.extend(history_turns)
        messages.append({"role": "user", "content": human_message})

        response = await self._llm.complete(messages, tools=None, json_mode=True)

        if response.content:
            try:
                result = extract_json(response.content)
                result.setdefault("action", "message")
                return result
            except json.JSONDecodeError:
                return {"action": "message", "message": response.content}
        return {"action": "message", "message": "No response generated."}

    # -- Validation --------------------------------------------------------

    def _validate_plan(
        self,
        plan: Dict[str, Any],
        rag_layers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Validate and correct URLs and field names in a query plan."""
        return validate_plan(plan, rag_layers)

    # -- Location resolution -----------------------------------------------

    async def _resolve_location(
        self, node: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve a root node (address/location/where) to ArcGIS geometry + source metadata."""
        node_type = node.get("type", "")

        if node_type == "address":
            address = node.get("address", "")
            result = await self._mcp.call_tool(
                "geocode", {"address": address},
                **({'progress_callback': self._progress_callback} if self._progress_callback is not None else {}),
            )
            candidates = result.get("candidates", [])
            if not candidates:
                raise ValueError(f"Geocode returned no candidates for: {address}")
            best = candidates[0]
            location = best.get("location", {})
            geometry = {
                "x": location.get("x"),
                "y": location.get("y"),
                "spatialReference": {"wkid": 4326},
            }
            source = {
                "type": "geocode",
                "address": address,
                "location": location,
                "score": best.get("score"),
                "candidates": candidates,
            }
            return {"geometry": geometry, "source": source}

        if node_type == "location":
            lon = node.get("lon") or node.get("longitude") or node.get("x")
            lat = node.get("lat") or node.get("latitude") or node.get("y")
            if lon is None or lat is None:
                raise ValueError("Location node missing lon/lat")
            geometry = {
                "x": float(lon),
                "y": float(lat),
                "spatialReference": {"wkid": 4326},
            }
            source = {
                "type": "coordinates",
                "location": {"x": float(lon), "y": float(lat)},
            }
            return {"geometry": geometry, "source": source}

        if node_type == "where":
            layer_url = node.get("layer_url", "")
            where = node.get("where", "1=1")
            result = await self._mcp.call_tool("query_features", {
                "layer_url": layer_url,
                "where": where,
                "return_geometry": True,
            }, **({'progress_callback': self._progress_callback} if self._progress_callback is not None else {}))
            features = result.get("features", [])
            if not features:
                raise ValueError(
                    f"Feature query returned no features for "
                    f"{node.get('layer')} WHERE {where}"
                )
            geometry = features[0].get("geometry", {})
            source = {
                "type": "feature_query",
                "layer": node.get("layer"),
                "layer_url": layer_url,
                "where": where,
                "features": features,
                "geometry": geometry,
            }
            return {"geometry": geometry, "source": source}

        # Fallback: try old dict format (latitude/longitude/address)
        lat = node.get("latitude") or node.get("lat")
        lon = node.get("longitude") or node.get("lon") or node.get("lng")
        address = node.get("address")
        if lat is not None and lon is not None:
            geometry = {
                "x": float(lon),
                "y": float(lat),
                "spatialReference": {"wkid": 4326},
            }
            return {
                "geometry": geometry,
                "source": {"type": "coordinates", "location": {"x": float(lon), "y": float(lat)}},
            }
        if address:
            node_copy = dict(node, type="address")
            return await self._resolve_location(node_copy)

        raise ValueError(f"Unknown root node type: {node_type!r}")

    # -- Result wrapping ---------------------------------------------------

    def _wrap_query_result(self, tool_result: Any) -> Dict[str, Any]:
        """Wrap execute_query_plan result in uniform {source, results} shape."""
        if not isinstance(tool_result, dict):
            return {"source": None, "results": []}

        if "error" in tool_result:
            error_msg = tool_result["error"]
            detail = tool_result.get("detail")
            if detail:
                error_msg = f"{error_msg}: {detail}"
            return {"source": None, "results": [], "error": error_msg}

        result_type = tool_result.get("type")

        # Spatial join: parent + children
        if result_type == "spatial_join":
            parent = tool_result.get("parent", {})
            source = {
                "type": "feature_query",
                "features": parent.get("features", []),
                "geometry": parent.get("geometry"),
                "layer": tool_result.get("layer"),
                "layer_url": tool_result.get("layer_url"),
            }
            return {"source": source, "results": tool_result.get("children", [])}

        # Multiple results wrapper (len(queries) > 1)
        if "results" in tool_result and isinstance(tool_result["results"], list):
            all_results: List[Dict[str, Any]] = []
            source = None
            for sub in tool_result["results"]:
                wrapped = self._wrap_query_result(sub)
                if wrapped.get("source") and not source:
                    source = wrapped["source"]
                all_results.extend(wrapped.get("results", []))
            return {"source": source, "results": all_results}

        # Flat single-layer result
        entry: Dict[str, Any] = {
            "layer": tool_result.get("layer"),
            "layer_url": tool_result.get("layer_url"),
        }
        if result_type == "count":
            entry["count"] = tool_result.get("count", 0)
            entry["type"] = "count"
        else:
            entry["features"] = tool_result.get("features", [])
            entry["count"] = tool_result.get("count", len(entry["features"]))
            entry["fields"] = tool_result.get("fields")
            entry["geometryType"] = tool_result.get("geometryType")
            entry["spatialReference"] = tool_result.get("spatialReference")
        return {"source": None, "results": [entry]}

    # -- Graph runtime path ------------------------------------------------

    async def _execute_via_graph(
        self,
        plan_result: Dict[str, Any],
        action: str,
        overall_start: float,
        rag_ms: float,
        plan_ms: float,
        validation_ms: float,
    ) -> Dict[str, Any]:
        """Execute a plan via the DAG-based graph runtime."""
        from core.orchestrator.graph import (
            GraphContext,
            GraphRuntime,
            expand_plan,
            PlanExpansionError,
            EXECUTOR_MAP,
        )
        from core.orchestrator.graph.context import ArtifactType
        from core.orchestrator.graph.resilience import CircuitBreaker, RetryBudget

        # Expand LLM plan → ExecutionGraph
        expand_start = time.perf_counter()
        try:
            graph = expand_plan(plan_result, rag_layers=self._last_rag_layers)
        except PlanExpansionError as exc:
            logger.error("Graph expansion failed: %s", exc)
            total_ms = (time.perf_counter() - overall_start) * 1000
            return self.build_response(
                action="error",
                message=f"Plan expansion failed: {exc}",
                execution_time_ms=total_ms,
                timing=self.build_timing(
                    rag_ms=rag_ms, plan_ms=plan_ms, validation_ms=validation_ms,
                ),
            )
        expansion_ms = (time.perf_counter() - expand_start) * 1000

        # Build context
        budget_limit = self._config.node_retry_budget if self._config else 5
        semaphore_limit = self._config.arcgis_max_concurrent if self._config else 10
        cb_threshold = self._config.circuit_breaker_threshold if self._config else 5
        correlation_id = str(uuid.uuid4())
        ctx = GraphContext(
            correlation_id=correlation_id,
            mcp_client=self._mcp,
            retry_budget=RetryBudget(max_retries=budget_limit),
            progress_callback=self._progress_callback,
            semaphore=asyncio.Semaphore(semaphore_limit),
            circuit_breaker=CircuitBreaker(failure_threshold=cb_threshold),
        )

        # Execute graph
        runtime = self._graph_runtime or GraphRuntime(EXECUTOR_MAP)
        graph_start = time.perf_counter()
        result = await runtime.execute(graph, ctx)
        graph_ms = (time.perf_counter() - graph_start) * 1000
        total_ms = (time.perf_counter() - overall_start) * 1000

        # Convert GraphResult → response shape
        return self._graph_result_to_response(
            result, ctx, graph, action, plan_result,
            total_ms, rag_ms, plan_ms, validation_ms, expansion_ms, graph_ms,
        )

    def _graph_result_to_response(
        self,
        result,
        ctx,
        graph,
        action: str,
        plan_result: Dict[str, Any],
        total_ms: float,
        rag_ms: float,
        plan_ms: float,
        validation_ms: float,
        expansion_ms: float,
        graph_ms: float,
    ) -> Dict[str, Any]:
        """Convert a GraphResult into the standard ExecuteResponse shape."""
        from core.orchestrator.graph.context import ArtifactType

        message = plan_result.get("message", "")

        # Build results from graph context artifacts
        results = []
        for artifact_key, meta in ctx.artifact_meta.items():
            node_id = meta.producer_node_id
            node = graph.nodes.get(node_id)
            if not node:
                continue
            raw = ctx.artifacts.get(artifact_key)
            data = raw if isinstance(raw, dict) else {"value": raw}

            # Proximity nodes produce compound blobs → decompose into 3 entries
            if (
                node.node_type == "proximity"
                and isinstance(data, dict)
                and "buffer_geometry" in data
            ):
                decomposed = _decompose_proximity(data, node)
                # Enrich proximity results with layer_name/layer_url
                layer_url = getattr(node, "layer_url", "") or ""
                resolved_name = self._resolve_layer_name(layer_url)
                for entry in decomposed:
                    entry["layer_url"] = entry.get("layer", "")
                    entry["layer_name"] = resolved_name
                results.extend(decomposed)
                continue

            result_entry = _artifact_to_result(data, meta, node)
            # Enrich feature_set results with layer_name/layer_url
            if result_entry.get("type") == "feature_set":
                layer_url = getattr(node, "layer_url", "") or ""
                result_entry["layer_url"] = layer_url
                result_entry["layer_name"] = self._resolve_layer_name(layer_url)
            results.append(result_entry)

        # Sort by display priority: geocode → buffer → distance_line → result
        _ROLE_ORDER = {"source": 0, "buffer": 1, "distance_line": 2, "result": 3}
        results.sort(
            key=lambda r: (
                0 if r.get("type") == "geocode" else 1,
                _ROLE_ORDER.get(r.get("role", "result"), 3),
            )
        )

        # Build execution_graph metadata
        edges = []
        node_timing_enriched = []
        for t in result.node_timing:
            node = graph.nodes.get(t.node_id)
            deps = list(node.depends_on) if node else []
            for dep in deps:
                edges.append({"source": dep, "target": t.node_id})
            node_timing_enriched.append({
                "node_id": t.node_id,
                "node_type": t.node_type,
                "ms": round(t.ms, 2),
                "retries": t.retries,
                "status": t.status,
                "depends_on": deps,
                "label": self._build_node_label(node) if node else t.node_id,
            })

        execution_graph = {
            "nodes_executed": len(result.node_timing),
            "parallel_groups": result.parallel_groups,
            "retry_budget_used": result.retry_budget_used,
            "errors": result.errors,
            "skipped": result.skipped,
            "artifacts_produced": result.artifacts_produced,
            "node_timing": node_timing_enriched,
            "edges": edges,
        }

        timing = self.build_timing(
            rag_ms=rag_ms,
            plan_ms=plan_ms,
            validation_ms=validation_ms,
            expansion_ms=expansion_ms,
            graph_ms=graph_ms,
        )

        return self.build_response(
            action=action,
            message=message,
            results=results,
            execution_time_ms=total_ms,
            timing=timing,
            execution_graph=execution_graph,
        )

    # -- Main execute pipeline ---------------------------------------------

    async def execute(
        self,
        query: str,
        session_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Execute a query through the full pipeline: plan -> validate -> MCP tool -> raw result."""
        overall_start = time.perf_counter()
        logger.info("Executing query: %s", query[:100])
        self._progress_callback = progress_callback

        query_id = str(uuid.uuid4())
        norm_query = _normalize_query(query)

        # Step 1: RAG retrieval
        rag_start = time.perf_counter()
        if self._rag_service is not None:
            context_str, rag_layers = await self._rag_service.build_context(query)
        else:
            context_str, rag_layers = await build_rag_context(query)
        self._last_rag_layers = rag_layers
        rag_ms = (time.perf_counter() - rag_start) * 1000
        logger.info("RAG context built (%.0f ms)", rag_ms)

        # Guard: if RAG returns no layers and no patterns, don't call LLM
        if not rag_layers and not context_str.strip():
            logger.warning("RAG returned empty context for execute: %s", query[:100])
            resp = self.build_response(
                action="message",
                message="No relevant layers or patterns found in the knowledge base for this query. Please ingest layer data first.",
                data=None,
            )
            resp["query_id"] = query_id
            return resp

        ctx_hash = _hash_context(context_str)
        cache_key = f"fcache:{norm_query}:{ctx_hash}"

        # Step 1.5: Check Redis feedback cache
        cached_response = await ResponseCache.get(norm_query, ctx_hash)
        if cached_response is not None:
            logger.info("Redis cache hit for query: %s", query[:80])
            cached_response["query_id"] = query_id
            if session_id:
                await ResponseCache.store_query_mapping(
                    session_id, query_id, cache_key
                )
                cached_msg = cached_response.get("message", "")
                await ConversationHistory.add_message(
                    session_id, "assistant", cached_msg
                )
            return cached_response

        # Step 2: Get the query plan
        plan_start = time.perf_counter()
        plan_result = await self._plan_from_context(
            query, context_str, session_id=session_id
        )
        plan_ms = (time.perf_counter() - plan_start) * 1000

        action = plan_result.get("action", "message")
        message = plan_result.get("message", "")

        # Validate URLs / field names against KB
        validation_start = time.perf_counter()
        if action in ("query", "analyze", "locate") and self._last_rag_layers:
            plan_result = self._validate_plan(plan_result, self._last_rag_layers)
        validation_ms = (time.perf_counter() - validation_start) * 1000

        # Non-executable actions (message, route)
        if action not in ("query", "analyze", "locate"):
            total_ms = (time.perf_counter() - overall_start) * 1000
            result = self.build_response(
                action=action,
                message=plan_result.get("message", ""),
                execution_time_ms=total_ms,
                timing=self.build_timing(plan_ms=plan_ms, validation_ms=validation_ms),
            )
            result["query_id"] = query_id
            return result

        # All executable actions go through the graph runtime
        result = await self._execute_via_graph(
            plan_result, action, overall_start, rag_ms, plan_ms, validation_ms,
        )
        result["query_id"] = query_id
        await self._post_execute(
            query, session_id, query_id, plan_result,
            norm_query, ctx_hash, cache_key, result,
        )
        return result

    async def _post_execute(
        self,
        query: str,
        session_id: Optional[str],
        query_id: str,
        plan_result: Dict[str, Any],
        norm_query: str,
        ctx_hash: str,
        cache_key: str,
        response: Dict[str, Any],
    ) -> None:
        """Cache response and store conversation history after successful execution."""
        await ResponseCache.set(norm_query, ctx_hash, response)
        if session_id:
            await ResponseCache.store_query_mapping(session_id, query_id, cache_key)
            action = response.get("action", "")
            message = response.get("message", "")
            await ConversationHistory.add_message(session_id, "user", query)
            await ConversationHistory.add_message(
                session_id, "assistant", f"Action: {action}. {message}"
            )
