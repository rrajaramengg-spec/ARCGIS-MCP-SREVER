"""
QueryHandler — RAG + LLM planning, validation, and query execution.
Extracts plan(), _validate_plan(), and the execute-query pipeline from the
monolithic orchestrator.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from async_lru import alru_cache

from core.llm_service import LLMService
from core.mcp_client import MCPClient
from core.rag import build_rag_context
from core.history import ConversationHistory
from core.response_cache import ResponseCache

from .base import BaseHandler, extract_json, register_handler

logger = logging.getLogger(__name__)


def _normalize_query(query: str) -> str:
    """Normalize query for cache key: lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", query.strip().lower())


def _hash_context(context_str: str) -> str:
    """Hash RAG context string for cache key."""
    return hashlib.md5(context_str.encode()).hexdigest()


@alru_cache(maxsize=128, ttl=300)
async def _cached_plan(
    normalized_query: str,
    context_hash: str,
    system_prompt: str,
    human_message: str,
    llm_service_id: int,
) -> Dict[str, Any]:
    """Module-level cached plan generation. NOT an instance method.

    The llm_service_id is id(llm_service) — used only to look up the service
    from the module-level registry, not as a meaningful cache key component.
    """
    llm = _llm_registry.get(llm_service_id)
    if llm is None:
        raise RuntimeError("LLM service not registered for cached plan call")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": human_message},
    ]

    # Call LLM directly — NO tool loop, NO tools.
    # This eliminates the latent double-execution risk.
    response = await llm.complete(messages, tools=None, json_mode=True)

    if response.content:
        try:
            result = extract_json(response.content)
            result.setdefault("action", "message")
            return result
        except json.JSONDecodeError:
            return {"action": "message", "message": response.content}
    return {"action": "message", "message": "No response generated."}


# Registry for LLM services used by the cached plan function
_llm_registry: Dict[int, Any] = {}


@register_handler("query")
class QueryHandler(BaseHandler):
    """Handles the full query pipeline: RAG → LLM → validate → execute."""

    def __init__(
        self,
        mcp: MCPClient,
        llm: LLMService,
        prompts: Dict[str, Any],
        tools_cache: List[Dict[str, Any]],
    ) -> None:
        super().__init__(mcp, llm)
        self._prompts = prompts
        self._tools_cache = tools_cache
        self._last_rag_layers: List[Dict[str, Any]] = []
        # Register LLM service for module-level cached plan function
        _llm_registry[id(llm)] = llm

    async def _get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get MCP tools formatted for OpenAI (cached)."""
        if not self._tools_cache:
            mcp_tools = await self._mcp.list_tools()
            self._tools_cache.extend(LLMService.mcp_tools_to_openai_format(mcp_tools))
            logger.info("Loaded %d MCP tools for LLM", len(self._tools_cache))
        return self._tools_cache

    async def plan(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a query plan via RAG + LLM without executing against ArcGIS.

        Calls LLM.complete() directly with tools=None and json_mode=True.
        Does NOT use run_tool_loop() — eliminates latent double-execution risk.
        """
        overall_start = time.perf_counter()
        logger.info("Planning query: %s", query[:100])

        # Step 1: RAG retrieval
        rag_start = time.perf_counter()
        context_str, rag_layers = await build_rag_context(query)
        self._last_rag_layers = rag_layers
        rag_ms = (time.perf_counter() - rag_start) * 1000
        logger.info("RAG context built (%.0f ms)", rag_ms)

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

        # Retrieve conversation history (if session_id provided)
        history_turns: List[Dict[str, Any]] = []
        if session_id:
            try:
                history_turns = await ConversationHistory.get_turns(session_id)
            except Exception as exc:
                logger.warning("History retrieval failed, proceeding without: %s", exc)

        # Call LLM plan — bypass cache when history exists (session-specific)
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
        """Generate a plan with conversation history injected.

        Message array: [system, user_1, assistant_1, ..., current_user_with_rag]
        """
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

    def _validate_plan(
        self,
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

    async def _resolve_location(
        self, node: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve a root node (address/location/where) to ArcGIS geometry + source metadata.

        Returns dict with keys ``geometry`` (ArcGIS JSON point/polygon) and
        ``source`` (metadata dict describing origin).
        """
        node_type = node.get("type", "")

        if node_type == "address":
            address = node.get("address", "")
            result = await self._mcp.call_tool("geocode", {"address": address}, progress_callback=self._progress_callback)
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
            }, progress_callback=self._progress_callback)
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

    def _wrap_query_result(self, tool_result: Any) -> Dict[str, Any]:
        """Wrap execute_query_plan result in uniform ``{source, results}`` shape."""
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

    async def _execute_locate(
        self,
        plan_result: Dict[str, Any],
        overall_start: float,
    ) -> Dict[str, Any]:
        """Execute a locate action: geocode/coords, optional children spatial lookup."""
        locate_payload = plan_result.get("locate")
        message = plan_result.get("message", "")

        # Support array or dict format
        if isinstance(locate_payload, list):
            locate_nodes = locate_payload
        elif isinstance(locate_payload, dict):
            locate_nodes = [locate_payload]
        else:
            total_ms = (time.perf_counter() - overall_start) * 1000
            logger.warning("Locate action missing payload, returning message-only")
            return self.build_response(
                action="locate",
                message=message or "Could not determine location from query.",
                execution_time_ms=total_ms,
            )

        async def _process_locate_node(
            node: Dict[str, Any],
        ) -> Dict[str, Any]:
            """Process one locate node: resolve location + optional children."""
            try:
                resolved = await self._resolve_location(node)
            except ValueError as exc:
                logger.error("Locate resolve failed: %s", exc)
                return {"source": {"error": str(exc)}, "results": []}

            source = resolved["source"]
            geometry = resolved["geometry"]
            results: List[Dict[str, Any]] = []

            children = node.get("children", [])
            if children:
                async def _locate_child(
                    child: Dict[str, Any], geom: dict = geometry
                ) -> Dict[str, Any]:
                    result = await self._mcp.call_tool("query_features", {
                        "layer_url": child.get("layer_url", ""),
                        "where": child.get("where", "1=1"),
                        "geometry_filter": geom,
                    }, progress_callback=self._progress_callback)
                    return {
                        "layer": child.get("layer"),
                        "layer_url": child.get("layer_url"),
                        "features": result.get("features", []),
                        "count": result.get("count", len(result.get("features", []))),
                        "join_type": "spatial",
                    }

                tasks = [_locate_child(c) for c in children]
                child_results = await asyncio.gather(*tasks, return_exceptions=True)
                for cr in child_results:
                    if isinstance(cr, Exception):
                        logger.error("Locate child query failed: %s", cr)
                    else:
                        results.append(cr)

            return {"source": source, "results": results}

        # Process all locate nodes in parallel
        node_tasks = [_process_locate_node(n) for n in locate_nodes]
        node_results = await asyncio.gather(*node_tasks, return_exceptions=True)

        all_sources: List[Dict[str, Any]] = []
        all_results: List[Dict[str, Any]] = []
        for nr in node_results:
            if isinstance(nr, Exception):
                logger.error("Locate node failed: %s", nr)
            else:
                all_sources.append(nr["source"])
                all_results.extend(nr["results"])

        source = all_sources[0] if len(all_sources) == 1 else all_sources
        total_ms = (time.perf_counter() - overall_start) * 1000

        return self.build_response(
            action="locate",
            message=message,
            data={"source": source, "results": all_results},
            execution_time_ms=total_ms,
        )

    async def _execute_analyze(
        self,
        plan_result: Dict[str, Any],
        overall_start: float,
    ) -> Dict[str, Any]:
        """Execute an analyze action: resolve location → buffer/proximity queries."""
        analyze_nodes = plan_result.get("analyze", [])
        message = plan_result.get("message", "")
        logger.info("Analyze plan: %s", json.dumps(analyze_nodes, default=str)[:2000])

        if not analyze_nodes:
            total_ms = (time.perf_counter() - overall_start) * 1000
            return self.build_response(
                action="analyze",
                message=message or "No analyze nodes provided.",
                execution_time_ms=total_ms,
            )

        all_results: List[Dict[str, Any]] = []
        source: Optional[Dict[str, Any]] = None

        for root_node in analyze_nodes:
            # Step 1: Resolve root to geometry + source
            try:
                resolved = await self._resolve_location(root_node)
            except ValueError as exc:
                logger.error("Analyze: failed to resolve location: %s", exc)
                total_ms = (time.perf_counter() - overall_start) * 1000
                return self.build_response(
                    action="analyze",
                    message=str(exc),
                    execution_time_ms=total_ms,
                )

            geometry = resolved["geometry"]
            source = resolved["source"]

            # Step 2: Process tool nodes (children of root)
            for tool_node in root_node.get("children", []):
                if tool_node.get("type") != "tool":
                    continue

                join_type = tool_node.get("join_type", "buffer")
                distance = tool_node.get("distance", 1000)
                unit = tool_node.get("unit", "meters")
                leaf_children = tool_node.get("children", [])
                logger.info("Analyze tool_node: join_type=%s, distance=%s, unit=%s, leaf_children=%s",
                            join_type, distance, unit, json.dumps(leaf_children, default=str)[:500])

                if join_type == "buffer":
                    # Create buffer polygon (no layer_url → returns buffer_geometry only)
                    buffer_result = await self._mcp.call_tool("buffer_and_query", {
                        "geometry": geometry,
                        "radius": distance,
                        "unit": unit,
                    }, progress_callback=self._progress_callback)
                    buffer_geometry = buffer_result.get("buffer_geometry")
                    if not buffer_geometry:
                        logger.error("buffer_and_query returned no buffer_geometry")
                        continue

                    # Insert _buffer_zone as a renderable result entry
                    all_results.append({
                        "layer": "_buffer_zone",
                        "type": "buffer_zone",
                        "features": [{
                            "geometry": buffer_geometry,
                            "attributes": {"radius": distance, "unit": unit},
                        }],
                        "count": 1,
                        "geometryType": "esriGeometryPolygon",
                        "spatialReference": buffer_geometry.get(
                            "spatialReference", {"wkid": 4326}
                        ),
                        "join_type": "buffer",
                    })

                    # Query each child layer with buffer as spatial filter
                    async def _buffer_child(
                        child: Dict[str, Any], bg: dict = buffer_geometry
                    ) -> Dict[str, Any]:
                        result = await self._mcp.call_tool("query_features", {
                            "layer_url": child.get("layer_url", ""),
                            "where": child.get("where", "1=1"),
                            "geometry_filter": bg,
                        }, progress_callback=self._progress_callback)
                        if isinstance(result, str):
                            logger.error("query_features returned string instead of dict: %s", result[:500])
                            result = {"features": [], "count": 0, "error": result}
                        return {
                            "layer": child.get("layer"),
                            "layer_url": child.get("layer_url"),
                            "features": result.get("features", []),
                            "count": result.get("count", len(result.get("features", []))),
                            "fields": result.get("fields"),
                            "geometryType": result.get("geometryType"),
                            "spatialReference": result.get("spatialReference"),
                            "join_type": "buffer",
                        }

                    tasks = [_buffer_child(c) for c in leaf_children]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, Exception):
                            logger.error("Buffer child query failed: %s", r)
                        else:
                            all_results.append(r)

                elif join_type == "proximity":
                    top = tool_node.get("top", 20)

                    async def _proximity_child(
                        child: Dict[str, Any],
                        geom: dict = geometry,
                        d: float = distance,
                        u: str = unit,
                        t: int = top,
                    ) -> Dict[str, Any]:
                        result = await self._mcp.call_tool("find_nearby", {
                            "layer_url": child.get("layer_url", ""),
                            "geometry": geom,
                            "radius": d,
                            "unit": u,
                            "where": child.get("where", "1=1"),
                            "max_results": t,
                        }, progress_callback=self._progress_callback)
                        return {
                            "layer": child.get("layer"),
                            "layer_url": child.get("layer_url"),
                            "features": result.get("features", []),
                            "count": result.get("count", 0),
                            "total_in_radius": result.get("total_in_radius"),
                            "search_radius": result.get("search_radius"),
                            "search_unit": result.get("search_unit"),
                            "join_type": "proximity",
                        }

                    tasks = [_proximity_child(c) for c in leaf_children]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, Exception):
                            logger.error("Proximity child query failed: %s", r)
                        else:
                            all_results.append(r)

                else:
                    logger.warning(
                        "Unrecognized join_type '%s' — skipping tool node",
                        join_type,
                    )

        total_ms = (time.perf_counter() - overall_start) * 1000
        return self.build_response(
            action="analyze",
            message=message,
            data={"source": source, "results": all_results},
            execution_time_ms=total_ms,
        )

    async def execute(
        self,
        query: str,
        session_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Execute a query through the full pipeline: plan → validate → MCP tool → raw result."""
        overall_start = time.perf_counter()
        logger.info("Executing query: %s", query[:100])
        self._progress_callback = progress_callback

        query_id = str(uuid.uuid4())
        norm_query = _normalize_query(query)

        # Step 1: RAG retrieval (needed for both cache key and planning)
        rag_start = time.perf_counter()
        context_str, rag_layers = await build_rag_context(query)
        self._last_rag_layers = rag_layers
        rag_ms = (time.perf_counter() - rag_start) * 1000
        logger.info("RAG context built (%.0f ms)", rag_ms)

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
            return cached_response

        # Step 2: Get the query plan (using pre-computed RAG context)
        plan_start = time.perf_counter()
        plan_result = await self._plan_from_context(
            query, context_str, session_id=session_id
        )
        plan_ms = (time.perf_counter() - plan_start) * 1000

        action = plan_result.get("action", "message")
        message = plan_result.get("message", "")

        # Step 1.5: Validate URLs / field names against KB
        validation_start = time.perf_counter()
        if action in ("query", "analyze", "locate") and self._last_rag_layers:
            plan_result = self._validate_plan(plan_result, self._last_rag_layers)
        validation_ms = (time.perf_counter() - validation_start) * 1000

        # Step 2: Handle locate from plan
        if action == "locate":
            result = await self._execute_locate(plan_result, overall_start)
            result["query_id"] = query_id
            await self._post_execute(query, session_id, query_id, plan_result, norm_query, ctx_hash, cache_key, result)
            return result

        # Step 2.5: Handle analyze from plan
        if action == "analyze":
            result = await self._execute_analyze(plan_result, overall_start)
            result["query_id"] = query_id
            await self._post_execute(query, session_id, query_id, plan_result, norm_query, ctx_hash, cache_key, result)
            return result

        # Step 3: Non-executable actions (route, message)
        if action != "query" or "query" not in plan_result:
            total_ms = (time.perf_counter() - overall_start) * 1000
            logger.info("Execute: non-query action '%s', skipping tool execution", action)
            result = self.build_response(
                action=action,
                message=message,
                execution_time_ms=total_ms,
                timing=self.build_timing(plan_ms=plan_ms, validation_ms=validation_ms),
            )
            result["query_id"] = query_id
            return result

        # Step 4: Execute the plan via execute_query_plan MCP tool
        tool_name = "execute_query_plan"
        tool_args = {"query_plan": json.dumps(plan_result)}
        tool_result = None

        tool_start = time.perf_counter()
        try:
            logger.info("Calling MCP tool: %s", tool_name)
            tool_result = await self._mcp.call_tool(tool_name, tool_args, progress_callback=self._progress_callback)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            err_msg = (
                str(exc).strip()
                or f"Tool {tool_name} failed:"
                f" {type(exc).__name__}"
            )
            tool_result = {"error": err_msg}
        tool_ms = (time.perf_counter() - tool_start) * 1000

        total_ms = (time.perf_counter() - overall_start) * 1000
        logger.info("Execute pipeline complete (%.0f ms total)", total_ms)

        # Wrap in uniform {source, results} shape
        uniform_data = self._wrap_query_result(tool_result)

        result = self.build_response(
            action=action,
            message=message,
            data=uniform_data,
            tool_name=tool_name,
            tool_args=tool_args,
            execution_time_ms=total_ms,
            timing=self.build_timing(
                plan_ms=plan_ms,
                validation_ms=validation_ms,
                tool_ms=tool_ms,
            ),
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
        """Cache response and store conversation turn after successful execution."""
        # Cache the response in Redis
        await ResponseCache.set(norm_query, ctx_hash, response)
        if session_id:
            await ResponseCache.store_query_mapping(session_id, query_id, cache_key)
            # Store conversation turn (plan JSON, not post-execution data)
            await ConversationHistory.add_turn(session_id, query, plan_result)
