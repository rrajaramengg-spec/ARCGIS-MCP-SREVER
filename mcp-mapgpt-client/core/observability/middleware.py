"""FastAPI correlation middleware.

Generates or extracts a request correlation ID, sets ContextVars,
and adds X-Request-ID to the response. Does NOT log request start/end —
the existing request_logging_and_rate_limit middleware handles that
and automatically benefits from correlation ID injection via the filter.

Uses a pure ASGI middleware (not BaseHTTPMiddleware) to ensure ContextVar
changes are visible to inner middleware and route handlers.

NOTE: BaseHTTPMiddleware (used by @app.middleware("http")) spawns a new
anyio task, which gets a COPY of the context at spawn time — not the
live parent context.  To bridge the gap the correlation ID is also stored
in ``scope["state"]["_correlation_id"]`` so the logging middleware can
re-establish it in its own task via ``request.state._correlation_id``.
"""

from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

from core.observability.context import request_id_var


_REQUEST_ID_HEADER = "x-request-id"


class CorrelationMiddleware:
    """Set correlation ID ContextVar for each HTTP request (pure ASGI)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract from request headers or generate
        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode() or uuid4().hex[:12]
        )
        token = request_id_var.set(request_id)

        # Store in scope state so BaseHTTPMiddleware-wrapped middleware can
        # re-establish the ContextVar in their (separate) task context.
        state = scope.setdefault("state", {})
        state["_correlation_id"] = request_id

        async def send_with_header(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)
