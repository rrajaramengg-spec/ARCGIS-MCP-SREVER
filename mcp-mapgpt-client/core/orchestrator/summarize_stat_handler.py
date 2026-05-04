"""
SummarizeStatHandler — field statistics via summarize_field MCP tool.
Extracts summarize_stat() from the monolithic orchestrator.
"""

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from core.llm_service import LLMService
from core.mcp_client import MCPClient

from .base import BaseHandler, register_handler

logger = logging.getLogger(__name__)


@register_handler("summarize_stat", prefix="/summarize-stat ")
class SummarizeStatHandler(BaseHandler):
    """Handles field statistics: plan → field classify → summarize_field → LLM."""

    def __init__(
        self,
        mcp: MCPClient,
        llm: LLMService,
        prompts: Dict[str, Any],
    ) -> None:
        super().__init__(mcp, llm)
        self._prompts = prompts

    async def summarize_stat(
        self,
        query: str,
        session_id: Optional[str] = None,
        plan_fn: Optional[Callable] = None,
        summarize_fn: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Summarize a field's statistics via the summarize_field MCP tool.

        Pipeline:
          1. Run LLM planning to identify layer_url, field, and where clause
          2. Extract target field via A/D hybrid (heuristic + LLM fallback)
          3. Call summarize_field MCP tool
          4. Pass statistics through LLM for natural language summary

        Args:
            query: User's natural language query.
            session_id: Optional session identifier.
            plan_fn: Callable for LLM planning (injected by orchestrator).
            summarize_fn: Callable for fallback summarization.

        Returns:
            SummarizeStatResponse-shaped dict.
        """
        start = time.perf_counter()
        logger.info("Summarize-stat query: %s", query[:100])

        # Step 1: Get LLM plan
        if plan_fn is None:
            raise ValueError("plan_fn must be provided for summarize_stat")
        plan_result = await plan_fn(query=query, session_id=session_id)
        plan_ms = (time.perf_counter() - start) * 1000
        action = plan_result.get("action", "message")

        # If LLM can't identify a layer, return message
        if action == "message" or "query" not in plan_result:
            total_ms = (time.perf_counter() - start) * 1000
            return {
                "action": "summarize_stat",
                "summary": plan_result.get("message", "Unable to identify a layer for summarization."),
                "statistics": None,
                "field_name": None,
                "layer_url": None,
                "feature_count": 0,
                "execution_time_ms": round(total_ms, 2),
                "timing": self.build_timing(plan_ms=plan_ms),
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
            # Try extracting field from WHERE clause
            where_match = re.match(r"^\s*(\w+)\s*[=<>!]", where_clause)
            if where_match:
                pass  # WHERE field is a filter, not summarization target

        # Step 2b: D-phase fallback — lightweight LLM call to classify field
        llm_classify_ms = 0.0
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
                llm_start = time.perf_counter()
                field_response = await self._llm.complete(field_messages, tools=None)
                llm_classify_ms = (time.perf_counter() - llm_start) * 1000
                if field_response.content:
                    target_field = field_response.content.strip().strip('"').strip("'")
                    logger.info("D-phase identified field: '%s'", target_field)
            except Exception as exc:
                logger.warning("D-phase LLM call failed: %s", exc)

        # If we still can't identify a field, fall back to existing summarize flow
        if not target_field or not layer_url:
            logger.info("Field identification failed, falling back to summarize flow")
            if summarize_fn is None:
                total_ms = (time.perf_counter() - start) * 1000
                return {
                    "action": "summarize_stat",
                    "summary": "Unable to identify field for summarization.",
                    "statistics": None,
                    "field_name": None,
                    "layer_url": layer_url or None,
                    "feature_count": 0,
                    "execution_time_ms": round(total_ms, 2),
                    "timing": self.build_timing(plan_ms=plan_ms, llm_ms=llm_classify_ms),
                }
            fallback = await summarize_fn(query=query, session_id=session_id)
            total_ms = (time.perf_counter() - start) * 1000
            return {
                "action": "summarize_stat",
                "summary": fallback.get("summary", ""),
                "statistics": None,
                "field_name": None,
                "layer_url": layer_url or None,
                "feature_count": fallback.get("feature_count", 0),
                "execution_time_ms": round(total_ms, 2),
                "timing": self.build_timing(plan_ms=plan_ms, llm_ms=llm_classify_ms),
            }

        # Step 3: Call summarize_field MCP tool
        tool_args = {
            "layer_url": layer_url,
            "field_name": target_field,
            "where": where_clause,
        }

        tool_start = time.perf_counter()
        try:
            logger.info("Calling summarize_field: %s", tool_args)
            stats_result = await self._mcp.call_tool("summarize_field", tool_args)
        except Exception as exc:
            logger.error("summarize_field failed: %s", exc)
            total_ms = (time.perf_counter() - start) * 1000
            return {
                "action": "summarize_stat",
                "summary": f"Failed to compute statistics: {exc}",
                "statistics": None,
                "field_name": target_field,
                "layer_url": layer_url,
                "feature_count": 0,
                "execution_time_ms": round(total_ms, 2),
                "timing": self.build_timing(plan_ms=plan_ms, llm_ms=llm_classify_ms),
            }
        tool_ms = (time.perf_counter() - tool_start) * 1000

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

        llm_start = time.perf_counter()
        try:
            summary_response = await self._llm.complete(messages, tools=None)
            summary_text = summary_response.content or "Unable to generate summary."
        except Exception as exc:
            logger.error("Summary LLM call failed: %s", exc)
            summary_text = f"Statistics for {target_field}: {stats_str}"
        llm_summary_ms = (time.perf_counter() - llm_start) * 1000

        total_ms = (time.perf_counter() - start) * 1000
        logger.info("Summarize-stat complete (%.0f ms)", total_ms)

        return {
            "action": "summarize_stat",
            "summary": summary_text,
            "statistics": stats_result if isinstance(stats_result, dict) else None,
            "field_name": target_field,
            "layer_url": layer_url,
            "feature_count": feature_count,
            "execution_time_ms": round(total_ms, 2),
            "timing": self.build_timing(
                plan_ms=plan_ms,
                llm_ms=llm_classify_ms + llm_summary_ms,
                tool_ms=tool_ms,
            ),
        }
