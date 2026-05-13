"""Structured exception hierarchy and error response model for mcp-mapgpt-client."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class MapGPTError(Exception):
    """Base exception for all mcp-mapgpt-client errors.

    Args:
        message: Human-readable error description.
        code: Machine-readable error code for programmatic handling.
        status_code: HTTP status code to return in API responses.
    """

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class QueryPlanError(MapGPTError):
    """LLM failed to produce a valid query plan."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="QUERY_PLAN_ERROR", status_code=400)


class ToolCallError(MapGPTError):
    """MCP tool execution failed.

    Args:
        message: Error description.
        tool_name: Name of the tool that failed.
    """

    def __init__(self, message: str, tool_name: str = "") -> None:
        super().__init__(message, code="TOOL_CALL_ERROR", status_code=502)
        self.tool_name = tool_name


class RAGContextError(MapGPTError):
    """RAG retrieval or ingestion failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="RAG_CONTEXT_ERROR", status_code=500)


class ConfigurationError(MapGPTError):
    """Raised when required configuration is missing or invalid.

    Wraps Pydantic ``ValidationError`` with a structured domain error
    so startup failures are clear in Docker logs.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", status_code=500)


class ErrorResponse(BaseModel):
    """Structured error response — flat JSON for ELK/Kibana compatibility.

    All fields are top-level (no nesting) for direct Elasticsearch indexing.
    """

    error: str = Field(..., description="Human-readable error message")
    code: str = Field(..., description="Machine-readable error code")
    detail: Optional[str] = Field(
        default=None, description="Additional diagnostic detail"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of when the error occurred",
    )
    service: str = Field(
        default="mcp-mapgpt-client",
        description="Service that produced the error",
    )
