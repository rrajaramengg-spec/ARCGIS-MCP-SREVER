"""
Base handler, ToolLoopResult, handler registry, and shared constants
for the modular orchestrator.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from core.llm_service import LLMResponse, LLMService
from core.mcp_client import MCPClient

logger = logging.getLogger(__name__)

# ── Handler Registry ─────────────────────────────────────────────────────

_HANDLER_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_handler(name: str, prefix: Optional[str] = None) -> Callable:
    """Decorator to register a handler class in the global registry.

    Args:
        name: Unique handler name (e.g. "query", "locate").
        prefix: Optional slash-command prefix for routing (e.g. "/locate ").
    """

    def decorator(cls: Type["BaseHandler"]) -> Type["BaseHandler"]:
        if name in _HANDLER_REGISTRY:
            raise ValueError(
                f"Duplicate handler registration: '{name}' is already registered "
                f"by {_HANDLER_REGISTRY[name]['cls'].__name__}"
            )
        _HANDLER_REGISTRY[name] = {
            "cls": cls,
            "prefix": prefix,
        }
        return cls

    return decorator


# ── ToolLoopResult ────────────────────────────────────────────────────────

@dataclass
class ToolLoopResult:
    """Typed result of a tool-calling loop."""

    response: LLMResponse
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Any = None
    iterations: int = 0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_ms: float = 0.0
    llm_ms: float = 0.0


# ── Tool → Action Mapping ────────────────────────────────────────────────

TOOL_ACTION_MAP: Dict[str, str] = {
    "geocode": "locate",
    "reverse_geocode": "locate",
    "query_features": "query",
    "spatial_join_query": "query",
    "join_layers": "query",
    "execute_query_plan": "query",
    "count_features": "query",
    "buffer_and_query": "query",
    "find_nearby": "query",
    "search_content": "search",
    "search_layers": "search",
    "summarize_field": "analyze",
    "get_feature_table": "analyze",
}


# ── JSON Extraction Helper ───────────────────────────────────────────────

def extract_json(content: str) -> Dict[str, Any]:
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


# ── BaseHandler ───────────────────────────────────────────────────────────

class BaseHandler:
    """Base class for all action handlers.

    Provides the shared tool-calling loop, response shaping, and timing helpers.
    Each subclass receives only the dependencies it needs via constructor injection.
    """

    def __init__(self, mcp: MCPClient, llm: LLMService) -> None:
        self._mcp = mcp
        self._llm = llm

    async def run_tool_loop(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_iterations: int = 10,
        progress_callback: Optional[Callable] = None,
    ) -> ToolLoopResult:
        """Execute the LLM tool-calling loop.

        Iterates: check tool_calls → build assistant msg → execute tools via
        MCP → append results → re-call LLM.  Stops when the LLM returns text
        (no tool_calls) or *max_iterations* is reached.

        Args:
            messages: Chat history (mutated in-place with tool results).
            tools: OpenAI-formatted tool definitions.
            max_iterations: Safety cap on loop iterations.

        Returns:
            ToolLoopResult with final response, last tool metadata, and timing.
        """
        # Initial LLM call
        llm_start = time.perf_counter()
        response = await self._llm.complete(messages, tools=tools if tools else None)
        total_llm_ms = (time.perf_counter() - llm_start) * 1000
        total_tool_ms = 0.0

        iteration = 0
        last_tool_name: Optional[str] = None
        last_tool_args: Optional[Dict[str, Any]] = None
        last_tool_result: Any = None

        while response.has_tool_calls and iteration < max_iterations:
            iteration += 1
            logger.info("Tool-calling iteration %d", iteration)

            # Add assistant message with tool calls
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_input),
                        },
                    }
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in response.tool_calls:
                logger.info("Executing MCP tool: %s", tc.tool_name)
                last_tool_name = tc.tool_name
                last_tool_args = tc.tool_input

                tool_start = time.perf_counter()
                try:
                    tool_result = await self._mcp.call_tool(
                        tc.tool_name, tc.tool_input,
                        progress_callback=progress_callback,
                    )
                    result_str = (
                        json.dumps(tool_result)
                        if not isinstance(tool_result, str)
                        else tool_result
                    )
                    last_tool_result = tool_result
                except Exception as exc:
                    logger.error("Tool %s failed: %s", tc.tool_name, exc)
                    err_msg = (
                        str(exc).strip()
                        or f"Tool {tc.tool_name} failed:"
                        f" {type(exc).__name__}"
                    )
                    result_str = json.dumps({"error": err_msg})
                    last_tool_result = {"error": err_msg}
                total_tool_ms += (time.perf_counter() - tool_start) * 1000

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "content": result_str,
                    }
                )

            # Re-call LLM with tool results
            llm_start = time.perf_counter()
            response = await self._llm.complete(
                messages, tools=tools if tools else None
            )
            total_llm_ms += (time.perf_counter() - llm_start) * 1000

        return ToolLoopResult(
            response=response,
            tool_name=last_tool_name,
            tool_args=last_tool_args,
            tool_result=last_tool_result,
            iterations=iteration,
            messages=messages,
            tool_ms=round(total_tool_ms, 2),
            llm_ms=round(total_llm_ms, 2),
        )

    @staticmethod
    def build_response(
        action: str,
        message: Optional[str] = None,
        data: Any = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        execution_time_ms: float = 0.0,
        timing: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Build a consistent ExecuteResponse-shaped dict."""
        return {
            "action": action,
            "message": message,
            "data": data,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "execution_time_ms": round(execution_time_ms, 2),
            "timing": timing,
        }

    @staticmethod
    def build_timing(**phases: float) -> Dict[str, float]:
        """Build a timing dict with a computed total_ms.

        Example:
            build_timing(rag_ms=150, llm_ms=2100, tool_ms=800)
            → {"rag_ms": 150, "llm_ms": 2100, "tool_ms": 800, "total_ms": 3050}
        """
        timing = {k: round(v, 2) for k, v in phases.items()}
        timing["total_ms"] = round(sum(phases.values()), 2)
        return timing
