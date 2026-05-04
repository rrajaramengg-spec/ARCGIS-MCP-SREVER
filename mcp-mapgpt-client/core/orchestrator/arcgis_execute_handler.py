"""
ArcgisExecuteHandler — direct MCP tool invocation via LLM.
Extracts arcgis_execute() from the monolithic orchestrator, using the
shared run_tool_loop() from BaseHandler.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from core.llm_service import LLMService
from core.mcp_client import MCPClient

from .base import BaseHandler, TOOL_ACTION_MAP, ToolLoopResult, register_handler

logger = logging.getLogger(__name__)


@register_handler("arcgis_execute", prefix="/arcgis-execute ")
class ArcgisExecuteHandler(BaseHandler):
    """Handles direct ArcGIS tool execution — no RAG, no structured planning."""

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

    async def _get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get MCP tools formatted for OpenAI (cached)."""
        if not self._tools_cache:
            mcp_tools = await self._mcp.list_tools()
            self._tools_cache.extend(LLMService.mcp_tools_to_openai_format(mcp_tools))
            logger.info("Loaded %d MCP tools for LLM", len(self._tools_cache))
        return self._tools_cache

    async def arcgis_execute(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Direct MCP tool invocation via LLM — no RAG, no structured planning.

        Gives the LLM access to all MCP ArcGIS tools and lets it
        autonomously select and chain tools. Returns raw tool results.

        Returns:
            ExecuteResponse-shaped dict with raw tool results.
        """
        overall_start = time.perf_counter()
        logger.info("Direct execute query: %s", query[:100])

        # Build messages with direct execute prompt
        system_prompt = self._prompts["direct_execute"]["system"]
        human_template = self._prompts["direct_execute"]["human"]
        human_message = human_template.format(query=query)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": human_message},
        ]

        # Get MCP tools
        tools = await self._get_openai_tools() if self._mcp.is_connected else []

        # Run shared tool-calling loop
        loop_result: ToolLoopResult = await self.run_tool_loop(
            messages, tools=tools, max_iterations=5
        )

        # Derive action from last tool name
        action = (
            TOOL_ACTION_MAP.get(loop_result.tool_name, "message")
            if loop_result.tool_name
            else "message"
        )

        total_ms = (time.perf_counter() - overall_start) * 1000
        logger.info(
            "Direct execute complete — iterations=%d, tool=%s, action=%s (%.0f ms)",
            loop_result.iterations, loop_result.tool_name, action, total_ms,
        )

        return self.build_response(
            action=action,
            message=loop_result.response.content or "",
            data=loop_result.tool_result,
            tool_name=loop_result.tool_name,
            tool_args=loop_result.tool_args,
            execution_time_ms=total_ms,
            timing=self.build_timing(
                llm_ms=loop_result.llm_ms,
                tool_ms=loop_result.tool_ms,
            ),
        )
