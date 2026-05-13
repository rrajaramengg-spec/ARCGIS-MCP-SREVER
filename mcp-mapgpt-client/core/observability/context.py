"""ContextVar definitions for request correlation.

These variables are set by CorrelationMiddleware and read by CorrelationFilter
to inject correlation metadata into every log record automatically.

Note: ContextVars do NOT propagate through the in-process MCP transport
(anyio task context is copied at spawn time, not shared dynamically).
"""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
service_name_var: ContextVar[str] = ContextVar("service_name", default="unknown")
