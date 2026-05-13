"""
ExecuteLLMHandler — RAG-augmented LLM tool-calling.
Combines RAG context injection (from /execute) with autonomous MCP
tool execution (from /arcgis-execute).
"""

import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from core.history import ConversationHistory
from core.llm_service import LLMService
from core.mcp_client import MCPClient
from core.rag import build_rag_context
from core.response_cache import ResponseCache

from .base import BaseHandler, TOOL_ACTION_MAP, ToolLoopResult, register_handler

logger = logging.getLogger(__name__)

EXECUTE_LLM_CACHE_TTL = 300  # 5 minutes


def _normalize_query(query: str) -> str:
    """Normalize query for cache key: lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", query.strip().lower())


def _hash_context(context_str: str) -> str:
    """Hash RAG context string for cache key."""
    return hashlib.md5(context_str.encode()).hexdigest()


@register_handler("execute_llm", prefix="/execute-llm ")
class ExecuteLLMHandler(BaseHandler):
    """RAG-augmented LLM tool-calling — combines semantic retrieval with
    autonomous MCP tool execution."""

    def __init__(
        self,
        mcp: MCPClient,
        llm: LLMService,
        prompts: Dict[str, Any],
        tools_cache: List[Dict[str, Any]],
        rag_service=None,
    ) -> None:
        super().__init__(mcp, llm)
        self._prompts = prompts
        self._tools_cache = tools_cache
        self._rag_service = rag_service

    async def _get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get MCP tools formatted for OpenAI (cached)."""
        if not self._tools_cache:
            mcp_tools = await self._mcp.list_tools()
            self._tools_cache.extend(LLMService.mcp_tools_to_openai_format(mcp_tools))
            logger.info("Loaded %d MCP tools for LLM", len(self._tools_cache))
        return self._tools_cache

    async def execute_llm(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RAG-augmented LLM tool-calling execution.

        Retrieves RAG context, injects it into the system prompt, runs the
        LLM tool-calling loop with MCP tools, caches and returns the result.

        Args:
            query: Natural language query.
            session_id: Optional session ID for history and feedback.

        Returns:
            ExecuteResponse-shaped dict.
        """
        overall_start = time.perf_counter()
        logger.info("Execute-LLM query: %s", query[:100])

        query_id = str(uuid.uuid4())
        norm_query = _normalize_query(query)

        # Step 1: RAG retrieval
        rag_start = time.perf_counter()
        if self._rag_service is not None:
            context_str, _rag_layers = await self._rag_service.build_context(query)
        else:
            context_str, _rag_layers = await build_rag_context(query)
        rag_ms = (time.perf_counter() - rag_start) * 1000
        logger.info("RAG context built (%.0f ms)", rag_ms)

        # Guard: if RAG returns no layers and no patterns, don't call LLM
        if not _rag_layers and not context_str.strip():
            logger.warning("RAG returned empty context for execute-llm: %s", query[:100])
            resp = self.build_response(
                action="message",
                message="No relevant layers or patterns found in the knowledge base for this query. Please ingest layer data first.",
                data=None,
            )
            resp["query_id"] = query_id
            return resp

        ctx_hash = _hash_context(context_str)
        cache_key = f"fcache:{norm_query}:{ctx_hash}"

        # Step 2: Check cache
        cached_response = await ResponseCache.get(norm_query, ctx_hash)
        if cached_response is not None:
            logger.info("Cache hit for execute-llm query: %s", query[:80])
            cached_response["query_id"] = query_id
            if session_id:
                await ResponseCache.store_query_mapping(
                    session_id, query_id, cache_key
                )
            return cached_response

        # Step 3: Build messages with RAG-augmented prompt
        system_prompt = self._prompts["execute_llm"]["system"]
        human_template = self._prompts["execute_llm"]["human"]
        human_message = human_template.format(context=context_str, query=query)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Inject conversation history if available
        if session_id:
            try:
                history_turns = await ConversationHistory.get_turns(session_id)
                messages.extend(history_turns)
            except Exception as exc:
                logger.warning("History retrieval failed: %s", exc)

        messages.append({"role": "user", "content": human_message})

        # Step 4: Get MCP tools and run tool-calling loop
        tools = await self._get_openai_tools() if self._mcp.is_connected else []

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
            "Execute-LLM complete — iterations=%d, tool=%s, action=%s (%.0f ms)",
            loop_result.iterations, loop_result.tool_name, action, total_ms,
        )

        response = self.build_response(
            action=action,
            message=loop_result.response.content or "",
            data=loop_result.tool_result,
            tool_name=loop_result.tool_name,
            tool_args=loop_result.tool_args,
            execution_time_ms=total_ms,
            timing=self.build_timing(
                rag_ms=rag_ms,
                llm_ms=loop_result.llm_ms,
                tool_ms=loop_result.tool_ms,
            ),
        )
        response["query_id"] = query_id

        # Step 5: Cache with short TTL and store history
        await ResponseCache.set(norm_query, ctx_hash, response, ttl=EXECUTE_LLM_CACHE_TTL)
        if session_id:
            await ResponseCache.store_query_mapping(session_id, query_id, cache_key)
            for msg in loop_result.messages:
                role = msg.get("role", "assistant")
                content = msg.get("content", "")
                if isinstance(content, dict):
                    content = json.dumps(content)
                await ConversationHistory.add_message(session_id, role, content or "")

        return response
