"""
SummarizeHandler — execute → filter → LLM summary.
Extracts summarize() and _filter_for_summary() from the monolithic orchestrator.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.llm_service import LLMService
from core.mcp_client import MCPClient

from .base import BaseHandler, register_handler

logger = logging.getLogger(__name__)


@register_handler("summarize", prefix="/summarize ")
class SummarizeHandler(BaseHandler):
    """Handles execute → filter → LLM summarization pipeline."""

    def __init__(
        self,
        mcp: MCPClient,
        llm: LLMService,
        prompts: Dict[str, Any],
    ) -> None:
        super().__init__(mcp, llm)
        self._prompts = prompts

    async def summarize(
        self,
        query: str,
        session_id: Optional[str] = None,
        execute_fn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a query and return an LLM-generated summary of the results.

        This is the ONLY path where ArcGIS data reaches the LLM.
        The data is filtered before being sent for summarization.

        Args:
            query: User's natural language query.
            session_id: Optional session identifier.
            execute_fn: Callable to execute queries (injected by orchestrator).

        Returns:
            SummarizeResponse-shaped dict with LLM summary.
        """
        overall_start = time.perf_counter()
        logger.info("Summarize query: %s", query[:100])

        # Step 1: Run the execute pipeline to get raw data
        if execute_fn is None:
            raise ValueError("execute_fn must be provided for summarize")
        execute_result = await execute_fn(query=query, session_id=session_id)

        action = execute_result.get("action", "message")
        data = execute_result.get("data")

        # If no tool was called (message-only), return the LLM message as summary
        if data is None:
            total_ms = (time.perf_counter() - overall_start) * 1000
            return {
                "action": action,
                "summary": execute_result.get("message", "No data to summarize."),
                "feature_count": 0,
                "execution_time_ms": round(total_ms, 2),
                "timing": self.build_timing(total_ms=0),
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
        llm_start = time.perf_counter()
        summary_response = await self._llm.complete(messages, tools=None)
        llm_ms = (time.perf_counter() - llm_start) * 1000
        summary_text = summary_response.content or "Unable to generate summary."

        total_ms = (time.perf_counter() - overall_start) * 1000
        logger.info("Summarize pipeline complete (%.0f ms total)", total_ms)

        return {
            "action": action,
            "summary": summary_text,
            "feature_count": total_count,
            "execution_time_ms": round(total_ms, 2),
            "timing": self.build_timing(llm_ms=llm_ms),
        }

    @staticmethod
    def _filter_for_summary(data: Any) -> Tuple[Any, int, Dict[str, str]]:
        """Filter ArcGIS result for LLM summarization.

        Strips geometry, system fields, and caps features at 10.
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
                for field_def in fs.fields:
                    name = field_def.get("name", "") if isinstance(field_def, dict) else getattr(field_def, "name", "")
                    alias = field_def.get("alias", "") if isinstance(field_def, dict) else getattr(field_def, "alias", "")
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
