"""ILLMService protocol — behavioral contract for LLM completion services."""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.llm_service import LLMResponse


@runtime_checkable
class ILLMService(Protocol):
    """Protocol for LLM completion services.

    Implementations must provide chat completion with optional tool-calling
    and a static method to convert MCP tool schemas to OpenAI format.
    """

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send messages to the LLM and get a completion response.

        Args:
            messages: Chat messages in OpenAI format.
            tools: Optional tool definitions for function calling.
            json_mode: If True, request JSON-formatted output.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        ...

    @staticmethod
    def mcp_tools_to_openai_format(
        mcp_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert MCP tool schemas to OpenAI function-calling format.

        Args:
            mcp_tools: Tool definitions from MCP server.

        Returns:
            Tool definitions in OpenAI format.
        """
        ...
