"""
Query orchestrator.
Implements the end-to-end async pipeline: RAG → LLM → MCP tool loop → response.
Replaces LangGraph state machines with a simple async pipeline.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.mcp_client import MCPClient
from core.llm_service import LLMService
from core.rag import build_rag_context

logger = logging.getLogger(__name__)


def _load_prompts() -> Dict[str, Any]:
    """Load prompts configuration from YAML."""
    config_path = Path(__file__).parent.parent / "prompts" / "config_prompts.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _extract_json(content: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling markdown fencing."""
    text = content.strip()
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()
    return json.loads(text)


class Orchestrator:
    """Orchestrates the query pipeline.

    Pipeline:
      1. Retrieve RAG context (few-shot examples + relevant docs)
      2. Build messages (system prompt + RAG context + user query)
      3. Call LLM with MCP tools
      4. Tool-calling loop until final text response
      5. Parse and return structured response
    """

    def __init__(self, mcp_client: MCPClient, llm_service: LLMService) -> None:
        self._mcp = mcp_client
        self._llm = llm_service
        self._prompts = _load_prompts()
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        self._last_rag_layers: List[Dict[str, Any]] = []

    async def _get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get MCP tools formatted for OpenAI."""
        if self._tools_cache is None:
            mcp_tools = await self._mcp.list_tools()
            self._tools_cache = LLMService.mcp_tools_to_openai_format(mcp_tools)
            logger.info("Loaded %d MCP tools for LLM", len(self._tools_cache))
        return self._tools_cache

    async def plan(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a query plan via RAG + LLM without executing against ArcGIS.

        This is the planning-only pipeline (formerly `process()`).
        Returns the LLM-generated structured JSON query plan.

        Args:
            query: User's natural language query.
            session_id: Optional session identifier.

        Returns:
            Structured response dict with action and payload.
        """
        overall_start = time.time()
        logger.info("Planning query: %s", query[:100])

        # Step 1: RAG retrieval
        retrieval_start = time.time()
        context_str, rag_layers = await build_rag_context(query)
        self._last_rag_layers = rag_layers
        retrieval_ms = (time.time() - retrieval_start) * 1000
        logger.info("RAG context built (%.0f ms)", retrieval_ms)

        # Step 2: Build messages
        system_prompt = self._prompts["query_instructions"]["system"]
        human_template = self._prompts["query_instructions"]["human"]
        human_message = human_template.format(context=context_str, query=query)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": human_message},
        ]

        # Step 3: Call LLM with tools
        tools = await self._get_openai_tools() if self._mcp.is_connected else []
        llm_start = time.time()
        response = await self._llm.complete(messages, tools=tools if tools else None)
        llm_ms = (time.time() - llm_start) * 1000
        logger.info("LLM call complete (%.0f ms)", llm_ms)

        # Step 4: Tool-calling loop
        max_iterations = 10
        iteration = 0
        while response.has_tool_calls and iteration < max_iterations:
            iteration += 1
            logger.info("Tool-calling iteration %d", iteration)

            # Add assistant message with tool calls to history
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
            }
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": json.dumps(tc.tool_input),
                    },
                }
                for tc in response.tool_calls
            ]
            messages.append(assistant_msg)

            # Execute each tool call and add results
            for tc in response.tool_calls:
                logger.info("Executing MCP tool: %s", tc.tool_name)
                try:
                    tool_result = await self._mcp.call_tool(tc.tool_name, tc.tool_input)
                    result_str = (
                        json.dumps(tool_result)
                        if not isinstance(tool_result, str)
                        else tool_result
                    )
                except Exception as exc:
                    logger.error("Tool %s failed: %s", tc.tool_name, exc)
                    result_str = json.dumps({"error": str(exc)})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "content": result_str,
                    }
                )

            # Re-call LLM with tool results
            response = await self._llm.complete(
                messages, tools=tools if tools else None
            )

        # Step 5: Parse response
        total_ms = (time.time() - overall_start) * 1000
        logger.info("Plan pipeline complete (%.0f ms total)", total_ms)

        if response.content:
            try:
                result = _extract_json(response.content)
                result.setdefault("action", "message")
                return result
            except json.JSONDecodeError:
                return {
                    "action": "message",
                    "message": response.content,
                }
        else:
            return {
                "action": "message",
                "message": "No response generated.",
            }

    async def _execute_locate(
        self,
        plan_result: Dict[str, Any],
        overall_start: float,
    ) -> Dict[str, Any]:
        """Execute a locate action from an LLM plan by calling geocode/reverse_geocode.

        Args:
            plan_result: LLM plan with action=locate and a locate payload.
            overall_start: Timestamp for execution timing.

        Returns:
            ExecuteResponse-shaped dict with geocode results.
        """
        locate_payload = plan_result.get("locate")
        message = plan_result.get("message", "")

        if not locate_payload or not isinstance(locate_payload, dict):
            total_ms = (time.time() - overall_start) * 1000
            logger.warning("Locate action missing payload, returning message-only")
            return {
                "action": "locate",
                "message": message or "Could not determine location from query.",
                "data": None,
                "tool_name": None,
                "tool_args": None,
                "execution_time_ms": round(total_ms, 2),
            }

        # Determine which MCP tool to call based on payload contents
        lat = locate_payload.get("latitude") or locate_payload.get("lat")
        lon = locate_payload.get("longitude") or locate_payload.get("lon") or locate_payload.get("lng")
        address = locate_payload.get("address")

        if lat is not None and lon is not None:
            tool_name = "reverse_geocode"
            tool_args = {"latitude": float(lat), "longitude": float(lon)}
        elif address:
            tool_name = "geocode"
            tool_args = {"address": address}
        else:
            total_ms = (time.time() - overall_start) * 1000
            logger.warning("Locate payload has neither address nor coordinates")
            return {
                "action": "locate",
                "message": message or "No address or coordinates provided.",
                "data": None,
                "tool_name": None,
                "tool_args": None,
                "execution_time_ms": round(total_ms, 2),
            }

        try:
            logger.info("Calling MCP tool: %s with args: %s", tool_name, tool_args)
            tool_result = await self._mcp.call_tool(tool_name, tool_args)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            tool_result = {"error": str(exc)}

        total_ms = (time.time() - overall_start) * 1000
        return {
            "action": "locate",
            "message": message,
            "data": tool_result,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "execution_time_ms": round(total_ms, 2),
        }

    def _validate_plan(
        self,
        plan: Dict[str, Any],
        rag_layers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Validate and correct URLs and field names in a query plan.

        Compares every layer_url and fields entry in the plan against the
        known-good values from the RAG knowledge base.  Fixes hallucinated
        URLs by matching on layer name, and strips unknown field names.

        Args:
            plan: LLM-generated query plan dict.
            rag_layers: Layer dicts from RAG retrieval (with url, fields).

        Returns:
            The plan dict, mutated in-place with corrections applied.
        """
        if plan.get("action") != "query" or "query" not in plan:
            return plan

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
            layer_name = (node.get("layer") or "").upper()
            layer_url = node.get("layer_url", "")

            # --- URL guardrail ---
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

            # --- Field name guardrail ---
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

        for query_node in plan.get("query", []):
            _fix_node(query_node)

        return plan

    async def execute(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a query through the full pipeline: plan → MCP tool execution → raw result.

        First calls plan() to get the LLM-generated query plan, then
        programmatically executes the plan via the execute_query_plan MCP tool.
        The raw ArcGIS data is returned directly to the caller and is NEVER
        sent back to the LLM.

        Args:
            query: User's natural language query.
            session_id: Optional session identifier.

        Returns:
            ExecuteResponse-shaped dict with raw ArcGIS data.
        """
        overall_start = time.time()
        logger.info("Executing query: %s", query[:100])

        # Slash-command prefix routing — bypass LLM planning for known commands
        prefix_routes = [
            ("/locate ", "locate"),
            ("/summarize-stat ", "summarize_stat"),
            ("/summarize ", "summarize"),
        ]
        for prefix, route_name in prefix_routes:
            if query.startswith(prefix):
                stripped_query = query[len(prefix):]
                logger.info("Prefix routing: '%s' → %s", prefix.strip(), route_name)
                if route_name == "locate":
                    locate_result = await self.locate(address=stripped_query)
                    # Wrap LocateResponse into ExecuteResponse shape for /execute callers
                    error_msg = locate_result.get("error")
                    message = (
                        error_msg
                        if error_msg
                        else locate_result.get("address")
                    )
                    return {
                        "action": "locate",
                        "message": message,
                        "data": locate_result,
                        "tool_name": "geocode",
                        "tool_args": {"address": stripped_query},
                        "execution_time_ms": locate_result.get("execution_time_ms", 0),
                    }
                elif route_name == "summarize_stat":
                    return await self.summarize_stat(query=stripped_query, session_id=session_id)
                elif route_name == "summarize":
                    return await self.summarize(query=stripped_query, session_id=session_id)

        # Step 1: Get the query plan from plan()
        plan_result = await self.plan(query=query, session_id=session_id)
        action = plan_result.get("action", "message")
        message = plan_result.get("message", "")

        # Step 1.5: Validate and correct URLs / field names against KB
        if action == "query" and self._last_rag_layers:
            plan_result = self._validate_plan(plan_result, self._last_rag_layers)

        # Step 2: If the action is not executable (route, message), return as-is
        if action == "locate":
            locate_result = await self._execute_locate(plan_result, overall_start)
            return locate_result

        if action != "query" or "query" not in plan_result:
            total_ms = (time.time() - overall_start) * 1000
            logger.info("Execute: non-query action '%s', skipping tool execution", action)
            return {
                "action": action,
                "message": message,
                "data": None,
                "tool_name": None,
                "tool_args": None,
                "execution_time_ms": round(total_ms, 2),
            }

        # Step 3: Execute the plan via execute_query_plan MCP tool
        tool_name = "execute_query_plan"
        tool_args = {"query_plan": json.dumps(plan_result)}
        tool_result = None

        try:
            logger.info("Calling MCP tool: %s", tool_name)
            tool_result = await self._mcp.call_tool(tool_name, tool_args)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            tool_result = {"error": str(exc)}

        total_ms = (time.time() - overall_start) * 1000
        logger.info("Execute pipeline complete (%.0f ms total)", total_ms)

        return {
            "action": action,
            "message": message,
            "data": tool_result,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "execution_time_ms": round(total_ms, 2),
        }

    async def locate(
        self,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Direct geocoding without LLM planning.

        Accepts an address string or lat/lon coordinates and calls the
        appropriate MCP geocoding tool directly.

        Args:
            address: Address string to geocode. May also be a "lat,lon" string.
            latitude: Latitude for reverse geocoding.
            longitude: Longitude for reverse geocoding.

        Returns:
            LocateResponse-shaped dict.
        """
        import re

        start = time.time()

        # Detect coordinate pattern in address string (e.g., "39.7,-104.9")
        if address and latitude is None and longitude is None:
            coord_match = re.match(
                r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", address
            )
            if coord_match:
                latitude = float(coord_match.group(1))
                longitude = float(coord_match.group(2))
                address = None

        # When address is provided, prefer it over zero-valued coordinates
        # (0, 0 is almost certainly a default/unset value, not Null Island)
        if address and latitude is not None and longitude is not None:
            if latitude == 0 and longitude == 0:
                latitude = None
                longitude = None

        if latitude is not None and longitude is not None:
            tool_name = "reverse_geocode"
            tool_args = {"latitude": latitude, "longitude": longitude}
        elif address:
            tool_name = "geocode"
            tool_args = {"address": address}
        else:
            total_ms = (time.time() - start) * 1000
            return {
                "action": "locate",
                "location": None,
                "address": None,
                "candidates": None,
                "score": None,
                "execution_time_ms": round(total_ms, 2),
            }

        try:
            logger.info("Direct locate — tool=%s args=%s", tool_name, tool_args)
            result = await self._mcp.call_tool(tool_name, tool_args)
        except Exception as exc:
            logger.error("Locate tool %s failed: %s", tool_name, exc)
            total_ms = (time.time() - start) * 1000
            return {
                "action": "locate",
                "location": None,
                "address": None,
                "candidates": None,
                "score": None,
                "execution_time_ms": round(total_ms, 2),
            }

        # Parse result from MCP tool
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass

        location = None
        resolved_address = None
        candidates = None
        score = None

        if isinstance(result, dict):
            # Check for error response from geocode tool
            if result.get("error"):
                error_msg = result.get("error")
                detail = result.get("detail", "")
                logger.error(
                    "Locate tool returned error: %s — %s", error_msg, detail
                )
                total_ms = (time.time() - start) * 1000
                return {
                    "action": "locate",
                    "location": None,
                    "address": None,
                    "candidates": None,
                    "score": None,
                    "error": f"{error_msg}: {detail}" if detail else error_msg,
                    "execution_time_ms": round(total_ms, 2),
                }

            # geocode returns candidates list; reverse_geocode returns address info
            candidates = result.get("candidates")
            if candidates and isinstance(candidates, list) and len(candidates) > 0:
                top = candidates[0]
                location = top.get("location")
                resolved_address = top.get("address")
                score = top.get("score")
            else:
                location = result.get("location")
                resolved_address = result.get("address")
                score = result.get("score")

        total_ms = (time.time() - start) * 1000
        return {
            "action": "locate",
            "location": location,
            "address": resolved_address,
            "candidates": candidates,
            "score": score,
            "execution_time_ms": round(total_ms, 2),
        }

    async def summarize_stat(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Summarize a field's statistics via the summarize_field MCP tool.

        Pipeline:
          1. Run LLM planning to identify layer_url, field, and where clause
          2. Extract target field via A/D hybrid (heuristic + LLM fallback)
          3. Call summarize_field MCP tool
          4. Pass statistics through LLM for natural language summary

        Falls back to the existing summarize flow if field identification fails.

        Args:
            query: User's natural language query.
            session_id: Optional session identifier.

        Returns:
            SummarizeStatResponse-shaped dict.
        """
        start = time.time()
        logger.info("Summarize-stat query: %s", query[:100])

        # Step 1: Get LLM plan
        plan_result = await self.plan(query=query, session_id=session_id)
        action = plan_result.get("action", "message")

        # If LLM can't identify a layer, return message
        if action == "message" or "query" not in plan_result:
            total_ms = (time.time() - start) * 1000
            return {
                "action": "summarize_stat",
                "summary": plan_result.get("message", "Unable to identify a layer for summarization."),
                "statistics": None,
                "field_name": None,
                "layer_url": None,
                "feature_count": 0,
                "execution_time_ms": round(total_ms, 2),
            }

        query_plan = plan_result.get("query", {})
        layer_url = query_plan.get("layer_url") or query_plan.get("url", "")
        where_clause = query_plan.get("where", "1=1")
        plan_fields = query_plan.get("fields") or query_plan.get("out_fields") or []

        # Normalize fields to list
        if isinstance(plan_fields, str):
            plan_fields = [f.strip() for f in plan_fields.split(",") if f.strip() and f.strip() != "*"]

        # Step 2: A-phase heuristic — extract target field
        KEY_FIELDS = {"OBJECTID", "FID", "GlobalID", "SHAPE", "SHAPE_Length", "SHAPE_Area"}
        candidate_fields = [f for f in plan_fields if f not in KEY_FIELDS]
        target_field = None

        if len(candidate_fields) == 1:
            target_field = candidate_fields[0]
            logger.info("A-phase heuristic: single field '%s'", target_field)
        elif len(candidate_fields) == 0 and where_clause != "1=1":
            # Try extracting field from WHERE clause (e.g., \"COUNTY = 'Springfield'\")
            import re
            where_match = re.match(r"^\s*(\w+)\s*[=<>!]", where_clause)
            if where_match:
                # The WHERE field is a filter, not the summarization target.
                # We need a D-phase fallback.
                pass

        # Step 2b: D-phase fallback — lightweight LLM call to classify field
        if target_field is None:
            logger.info("D-phase fallback: asking LLM to identify target field")
            try:
                field_prompt = (
                    f"Given the user's question: \"{query}\"\n"
                    f"And the available fields from the layer: {plan_fields or 'unknown'}\n"
                    f"Which single field should be statistically summarized? "
                    f"Reply with ONLY the field name, nothing else."
                )
                field_messages: List[Dict[str, Any]] = [
                    {"role": "system", "content": "You are a field classification assistant. Reply with only a single field name."},
                    {"role": "user", "content": field_prompt},
                ]
                field_response = await self._llm.complete(field_messages, tools=None)
                if field_response.content:
                    target_field = field_response.content.strip().strip('"').strip("'")
                    logger.info("D-phase identified field: '%s'", target_field)
            except Exception as exc:
                logger.warning("D-phase LLM call failed: %s", exc)

        # If we still can't identify a field, fall back to existing summarize flow
        if not target_field or not layer_url:
            logger.info("Field identification failed, falling back to summarize flow")
            fallback = await self.summarize(query=query, session_id=session_id)
            total_ms = (time.time() - start) * 1000
            return {
                "action": "summarize_stat",
                "summary": fallback.get("summary", ""),
                "statistics": None,
                "field_name": None,
                "layer_url": layer_url or None,
                "feature_count": fallback.get("feature_count", 0),
                "execution_time_ms": round(total_ms, 2),
            }

        # Step 3: Call summarize_field MCP tool
        tool_args = {
            "layer_url": layer_url,
            "field_name": target_field,
            "where": where_clause,
        }

        try:
            logger.info("Calling summarize_field: %s", tool_args)
            stats_result = await self._mcp.call_tool("summarize_field", tool_args)
        except Exception as exc:
            logger.error("summarize_field failed: %s", exc)
            total_ms = (time.time() - start) * 1000
            return {
                "action": "summarize_stat",
                "summary": f"Failed to compute statistics: {exc}",
                "statistics": None,
                "field_name": target_field,
                "layer_url": layer_url,
                "feature_count": 0,
                "execution_time_ms": round(total_ms, 2),
            }

        # Parse stats result
        if isinstance(stats_result, str):
            try:
                stats_result = json.loads(stats_result)
            except json.JSONDecodeError:
                pass

        feature_count = 0
        if isinstance(stats_result, dict):
            feature_count = stats_result.get("count", 0)

        # Step 4: LLM summary of statistics
        summarize_prompts = self._prompts.get("summarize_field_result", {})
        system_prompt = summarize_prompts.get(
            "system",
            "You are a data analyst. Summarize field statistics into a concise natural language response.",
        )
        human_template = summarize_prompts.get(
            "human",
            "Query: {query}\n\nField: {field_name}\nStatistics: {statistics}\n\nProvide a concise summary.",
        )

        stats_str = json.dumps(stats_result, default=str)
        human_message = human_template.format(
            query=query, field_name=target_field, statistics=stats_str
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": human_message},
        ]

        try:
            summary_response = await self._llm.complete(messages, tools=None)
            summary_text = summary_response.content or "Unable to generate summary."
        except Exception as exc:
            logger.error("Summary LLM call failed: %s", exc)
            summary_text = f"Statistics for {target_field}: {stats_str}"

        total_ms = (time.time() - start) * 1000
        logger.info("Summarize-stat complete (%.0f ms)", total_ms)

        return {
            "action": "summarize_stat",
            "summary": summary_text,
            "statistics": stats_result if isinstance(stats_result, dict) else None,
            "field_name": target_field,
            "layer_url": layer_url,
            "feature_count": feature_count,
            "execution_time_ms": round(total_ms, 2),
        }

    @staticmethod
    def _filter_for_summary(data: Any) -> tuple:
        """Filter ArcGIS result for LLM summarization.

        Strips geometry, system fields, and caps features at 10.
        Uses FeatureSet for typed access when available, with dict fallback.

        Returns:
            (filtered_data, total_feature_count, field_aliases)
        """
        SYSTEM_FIELDS = {"SHAPE", "SHAPE_Length", "SHAPE_Area", "GlobalID", "OBJECTID"}

        if not isinstance(data, dict):
            return data, 0, {}

        # Count-only result — pass through
        if "count" in data and "features" not in data:
            return data, 0, {}

        features = data.get("features")
        if not features or not isinstance(features, list):
            return data, 0, {}

        total_count = len(features)
        field_aliases: Dict[str, str] = {}

        # Try FeatureSet-based typed access
        try:
            from arcgis.features import FeatureSet

            fs = FeatureSet.from_dict(data)

            # Extract field aliases
            if hasattr(fs, "fields") and fs.fields:
                for field in fs.fields:
                    name = field.get("name", "") if isinstance(field, dict) else getattr(field, "name", "")
                    alias = field.get("alias", "") if isinstance(field, dict) else getattr(field, "alias", "")
                    if name and alias and name != alias:
                        field_aliases[name] = alias

            # Use typed Feature.attributes access
            capped = fs.features[:10]
            filtered = []
            for feat in capped:
                clean = {
                    "attributes": {
                        k: v
                        for k, v in feat.attributes.items()
                        if k not in SYSTEM_FIELDS
                    }
                }
                filtered.append(clean)

            result = {**data, "features": filtered}
            result.pop("geometry", None)
            return result, total_count, field_aliases

        except Exception:
            pass

        # Fallback: dict-based filtering
        capped = features[:10]
        filtered = []
        for feat in capped:
            clean = {}
            if "attributes" in feat:
                clean["attributes"] = {
                    k: v
                    for k, v in feat["attributes"].items()
                    if k not in SYSTEM_FIELDS
                }
            filtered.append(clean)

        result = {**data, "features": filtered}
        result.pop("geometry", None)
        return result, total_count, field_aliases

    async def summarize(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a query and return an LLM-generated summary of the results.

        This is the ONLY path where ArcGIS data reaches the LLM.
        The data is filtered (geometry stripped, system fields removed,
        capped at 10 features) before being sent for summarization.

        Args:
            query: User's natural language query.
            session_id: Optional session identifier.

        Returns:
            SummarizeResponse-shaped dict with LLM summary.
        """
        overall_start = time.time()
        logger.info("Summarize query: %s", query[:100])

        # Step 1: Run the execute pipeline to get raw data
        execute_result = await self.execute(query=query, session_id=session_id)

        action = execute_result.get("action", "message")
        data = execute_result.get("data")

        # If no tool was called (message-only), return the LLM message as summary
        if data is None:
            total_ms = (time.time() - overall_start) * 1000
            return {
                "action": action,
                "summary": execute_result.get("message", "No data to summarize."),
                "feature_count": 0,
                "execution_time_ms": round(total_ms, 2),
            }

        # Step 2: Filter data for summarization
        filtered_data, total_count, field_aliases = self._filter_for_summary(data)

        # Step 3: Build summarize prompt
        summarize_prompts = self._prompts.get("summarize_arcgis_result", {})
        system_prompt = summarize_prompts.get("system", "Summarize the following ArcGIS query results.")
        human_template = summarize_prompts.get("human", "Query: {query}\n\nResults: {results}")

        # Add truncation notice if applicable
        results_str = json.dumps(filtered_data, default=str)
        if total_count > 10:
            results_str += f"\n\n[Note: Showing 10 of {total_count} total features]"

        # Add field alias mapping if available
        if field_aliases:
            alias_str = "\n".join(f"  {k} → {v}" for k, v in field_aliases.items())
            results_str += f"\n\n[Field Aliases]\n{alias_str}"

        human_message = human_template.format(query=query, results=results_str)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": human_message},
        ]

        # Step 4: Call LLM for summary (no tools — pure text completion)
        summary_response = await self._llm.complete(messages, tools=None)
        summary_text = summary_response.content or "Unable to generate summary."

        total_ms = (time.time() - overall_start) * 1000
        logger.info("Summarize pipeline complete (%.0f ms total)", total_ms)

        return {
            "action": action,
            "summary": summary_text,
            "feature_count": total_count,
            "execution_time_ms": round(total_ms, 2),
        }
