"""
LLM service using direct OpenAI SDK (replaces LangChain wrappers).
Wraps openai.AsyncAzureOpenAI for chat completions with tool-calling support.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import openai

from core.config import ClientConfig

logger = logging.getLogger(__name__)


@dataclass
class ToolCallResult:
    """Represents a tool call requested by the LLM."""

    tool_call_id: str
    tool_name: str
    tool_input: Dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM completion call."""

    content: Optional[str] = None
    tool_calls: List[ToolCallResult] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMService:
    """Service for LLM interactions using Azure OpenAI directly."""

    def __init__(self, config: ClientConfig) -> None:
        self._client = openai.AsyncAzureOpenAI(
            api_key=config.azure_openai_api_key,
            azure_endpoint=config.azure_openai_endpoint,
            api_version=config.azure_openai_api_version,
        )
        self._deployment = config.azure_openai_deployment
        self._max_tokens = config.llm_max_tokens

        logger.info(
            "LLMService initialised — deployment=%s",
            self._deployment,
        )

    @staticmethod
    def mcp_tools_to_openai_format(
        mcp_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert MCP tool definitions to OpenAI function-calling format.

        Args:
            mcp_tools: List of MCP tool dicts with name, description, inputSchema.

        Returns:
            List of OpenAI-formatted tool definitions.
        """
        openai_tools = []
        for t in mcp_tools:
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("inputSchema", {}),
                    },
                }
            )
        return openai_tools

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Call the LLM with messages and optional tools.

        Args:
            messages: Chat messages in OpenAI format.
            tools: Optional OpenAI-formatted tool definitions.
            json_mode: If True, set response_format={"type": "json_object"}.

        Returns:
            LLMResponse with either content or tool_calls.
        """
        kwargs: Dict[str, Any] = {
            "model": self._deployment,
            "messages": messages,
            "max_completion_tokens": self._max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        logger.debug(
            "LLM call — %d messages, %d tools", len(messages), len(tools or [])
        )

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        result = LLMResponse()

        if message.content:
            result.content = message.content

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {"raw": tc.function.arguments}

                result.tool_calls.append(
                    ToolCallResult(
                        tool_call_id=tc.id,
                        tool_name=tc.function.name,
                        tool_input=tool_input,
                    )
                )

        logger.debug(
            "LLM response — content=%s, tool_calls=%d",
            "yes" if result.content else "no",
            len(result.tool_calls),
        )
        return result
