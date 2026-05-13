"""Unit tests for core.observability — filters, middleware, formatters."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI

from core.observability.context import request_id_var, service_name_var
from core.observability.filters import CorrelationFilter, SanitizingFilter
from core.observability.formatters import get_json_formatter, get_text_formatter
from core.observability.middleware import CorrelationMiddleware
from core.observability import setup_logging, get_request_id


# ---------------------------------------------------------------------------
# Task 2.6: CorrelationFilter tests
# ---------------------------------------------------------------------------
class TestCorrelationFilter:
    """CorrelationFilter reads ContextVars and injects into LogRecord."""

    def test_default_values_when_no_context(self):
        """Outside a request, request_id defaults to '-'."""
        # Reset ContextVars to simulate clean state (other tests may pollute)
        tok_rid = request_id_var.set("-")
        tok_svc = service_name_var.set("unknown")
        try:
            filt = CorrelationFilter()
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="hello", args=(), exc_info=None,
            )
            result = filt.filter(record)
            assert result is True
            assert record.request_id == "-"
            assert record.service == "unknown"
        finally:
            request_id_var.reset(tok_rid)
            service_name_var.reset(tok_svc)

    def test_reads_contextvar_values(self):
        """When ContextVars are set, filter injects their values."""
        filt = CorrelationFilter()
        tok_rid = request_id_var.set("abc123def456")
        tok_svc = service_name_var.set("mcp-mapgpt-client")
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="hello", args=(), exc_info=None,
            )
            filt.filter(record)
            assert record.request_id == "abc123def456"
            assert record.service == "mcp-mapgpt-client"
        finally:
            request_id_var.reset(tok_rid)
            service_name_var.reset(tok_svc)

    def test_always_returns_true(self):
        """Filter should never suppress records."""
        filt = CorrelationFilter()
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="debug", args=(), exc_info=None,
        )
        assert filt.filter(record) is True


# ---------------------------------------------------------------------------
# Task 2.7: SanitizingFilter tests
# ---------------------------------------------------------------------------
class TestSanitizingFilter:
    """SanitizingFilter redacts known sensitive field names."""

    def test_password_redacted(self):
        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.password = "secret123"
        filt.filter(record)
        assert record.password == "[REDACTED]"

    def test_token_redacted(self):
        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.token = "eyJhbGci..."
        filt.filter(record)
        assert record.token == "[REDACTED]"

    def test_api_key_redacted(self):
        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.api_key = "sk-12345"
        filt.filter(record)
        assert record.api_key == "[REDACTED]"

    def test_non_sensitive_passthrough(self):
        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.user_id = 42
        record.query = "show all psap"
        filt.filter(record)
        assert record.user_id == 42
        assert record.query == "show all psap"

    def test_multiple_sensitive_fields(self):
        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.password = "pw1"
        record.secret = "sec1"
        record.authorization = "Bearer xxx"
        filt.filter(record)
        assert record.password == "[REDACTED]"
        assert record.secret == "[REDACTED]"
        assert record.authorization == "[REDACTED]"

    def test_always_returns_true(self):
        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        assert filt.filter(record) is True


# ---------------------------------------------------------------------------
# Task 2.8: CorrelationMiddleware tests
# ---------------------------------------------------------------------------
class TestCorrelationMiddleware:
    """CorrelationMiddleware sets ContextVars and response header."""

    def _make_app(self):
        app = FastAPI()
        app.add_middleware(CorrelationMiddleware)

        @app.get("/test")
        async def test_route():
            return {"request_id": request_id_var.get()}

        return app

    def test_generates_request_id(self):
        app = self._make_app()
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        rid = response.headers.get("X-Request-ID")
        assert rid is not None
        assert len(rid) == 12
        # Body should contain the same ID
        assert response.json()["request_id"] == rid

    def test_propagates_incoming_header(self):
        app = self._make_app()
        client = TestClient(app)
        response = client.get("/test", headers={"X-Request-ID": "custom-id-123"})
        assert response.headers["X-Request-ID"] == "custom-id-123"
        assert response.json()["request_id"] == "custom-id-123"

    def test_response_always_has_header(self):
        app = self._make_app()
        client = TestClient(app)
        response = client.get("/test")
        assert "X-Request-ID" in response.headers

    def test_no_request_logging(self, caplog):
        """CorrelationMiddleware should NOT log request start/end."""
        app = self._make_app()
        client = TestClient(app)
        with caplog.at_level(logging.INFO, logger="core.observability.middleware"):
            response = client.get("/test")
        # No log records from the middleware itself
        middleware_logs = [
            r for r in caplog.records
            if r.name == "core.observability.middleware"
        ]
        assert len(middleware_logs) == 0

    def test_stores_id_in_scope_state(self):
        """CorrelationMiddleware stores ID in scope state for BaseHTTPMiddleware bridge."""
        app = FastAPI()
        captured = {}

        # @app.middleware must be registered BEFORE add_middleware(Correlation)
        # so that Correlation ends up outermost after Starlette's insert(0)+reversed build.
        @app.middleware("http")
        async def inner_middleware(request, call_next):
            # BaseHTTPMiddleware task — read from scope state
            captured["state_id"] = request.scope.get("state", {}).get("_correlation_id")
            return await call_next(request)

        app.add_middleware(CorrelationMiddleware)

        @app.get("/test")
        async def test_route():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test", headers={"X-Request-ID": "scope-test-123"})
        assert response.status_code == 200
        # scope state should always have the ID
        assert captured["state_id"] == "scope-test-123"


# ---------------------------------------------------------------------------
# Task 2.9: Formatter output tests
# ---------------------------------------------------------------------------
class TestJsonFormatter:
    """JSON formatter produces valid single-line JSON."""

    def test_json_output_structure(self):
        formatter = get_json_formatter()
        record = logging.LogRecord(
            name="core.handler", level=logging.INFO, pathname="handler.py",
            lineno=42, msg="Query executed", args=(), exc_info=None,
        )
        record.request_id = "abc123def456"
        record.service = "mcp-mapgpt-client"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "core.handler"
        assert parsed["message"] == "Query executed"
        assert parsed["request_id"] == "abc123def456"
        assert parsed["service"] == "mcp-mapgpt-client"
        assert parsed["lineno"] == 42
        assert "timestamp" in parsed

    def test_json_single_line(self):
        formatter = get_json_formatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.request_id = "-"
        record.service = "test"
        output = formatter.format(record)
        assert "\n" not in output


class TestTextFormatter:
    """Text formatter includes request_id in output."""

    def test_text_includes_request_id(self):
        formatter = get_text_formatter()
        record = logging.LogRecord(
            name="core.handler", level=logging.INFO, pathname="handler.py",
            lineno=42, msg="Query executed", args=(), exc_info=None,
        )
        record.request_id = "abc123def456"
        output = formatter.format(record)
        assert "[req=abc123def456]" in output
        assert "Query executed" in output
        assert "[INFO]" in output

    def test_text_default_request_id(self):
        formatter = get_text_formatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        record.request_id = "-"
        output = formatter.format(record)
        assert "[req=-]" in output


# ---------------------------------------------------------------------------
# Task 2.10: ContextVar non-propagation regression guard
# ---------------------------------------------------------------------------
class TestContextVarNonPropagation:
    """Verify ContextVars do NOT propagate through anyio task groups.

    This guards against the assumption that in-process MCP tools
    receive the HTTP request's correlation ID.
    """

    @pytest.mark.asyncio
    async def test_contextvar_not_shared_across_task_group(self):
        import anyio

        request_id_var.set("-")  # reset to default
        captured_in_child = []

        async def child_task():
            captured_in_child.append(request_id_var.get())

        # Spawn child task (simulates MCP server task at startup)
        async with anyio.create_task_group() as tg:
            tg.start_soon(child_task)

        # Child sees the default value
        assert captured_in_child[0] == "-"

    @pytest.mark.asyncio
    async def test_contextvar_set_after_spawn_not_visible(self):
        """Context set in parent AFTER child spawn is NOT visible to child."""
        import anyio

        request_id_var.set("-")
        captured_values = []
        event = anyio.Event()
        parent_ready = anyio.Event()

        async def child_task():
            parent_ready.set()  # signal parent we're running
            await event.wait()  # wait for parent to set the var
            captured_values.append(request_id_var.get())

        async with anyio.create_task_group() as tg:
            tg.start_soon(child_task)
            await parent_ready.wait()
            # Set var AFTER child was spawned
            request_id_var.set("new-request-id")
            event.set()

        # Child should NOT see the parent's update
        assert captured_values[0] == "-"


# ---------------------------------------------------------------------------
# setup_logging / get_request_id integration
# ---------------------------------------------------------------------------
class TestSetupLogging:
    """Verify setup_logging configures root logger correctly."""

    def test_json_format(self):
        setup_logging(service_name="test", log_format="json")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        from pythonjsonlogger.json import JsonFormatter
        assert isinstance(handler.formatter, JsonFormatter)

    def test_text_format(self):
        setup_logging(service_name="test", log_format="text")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler.formatter, logging.Formatter)
        assert "req=" in handler.formatter._fmt

    def test_correlation_filter_attached(self):
        setup_logging(service_name="test", correlation_enabled=True)
        root = logging.getLogger()
        handler = root.handlers[0]
        filter_types = [type(f).__name__ for f in handler.filters]
        assert "CorrelationFilter" in filter_types
        assert "SanitizingFilter" in filter_types

    def test_correlation_filter_skipped(self):
        setup_logging(service_name="test", correlation_enabled=False)
        root = logging.getLogger()
        handler = root.handlers[0]
        filter_types = [type(f).__name__ for f in handler.filters]
        assert "CorrelationFilter" not in filter_types
        assert "SanitizingFilter" in filter_types

    def test_noisy_loggers_suppressed(self):
        setup_logging(service_name="test")
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING


class TestGetRequestId:
    """get_request_id returns current ContextVar value."""

    def test_default_value(self):
        tok = request_id_var.set("-")
        try:
            assert get_request_id() == "-"
        finally:
            request_id_var.reset(tok)

    def test_set_value(self):
        tok = request_id_var.set("test-request-123")
        try:
            assert get_request_id() == "test-request-123"
        finally:
            request_id_var.reset(tok)
