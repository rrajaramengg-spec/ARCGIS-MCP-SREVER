"""Integration tests for observability — JSON output, correlation ID, X-Request-ID header."""

import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from core.observability import setup_logging
from core.observability.context import request_id_var
from core.observability.middleware import CorrelationMiddleware


def _make_app(correlation: bool = True) -> FastAPI:
    """Create a minimal FastAPI app with observability wired up."""
    app = FastAPI()
    if correlation:
        app.add_middleware(CorrelationMiddleware)

    @app.get("/test")
    async def test_route():
        logger = logging.getLogger("test.route")
        logger.info("test log message")
        return {"ok": True, "request_id": request_id_var.get()}

    return app


# ---------------------------------------------------------------------------
# Task 3.4: JSON output format
# ---------------------------------------------------------------------------
class TestJsonOutputFormat:
    """Verify JSON-structured log output with LOG_FORMAT=json."""

    def test_json_log_output(self):
        stream = StringIO()
        handler = logging.StreamHandler(stream)

        setup_logging(
            service_name="test-json",
            log_level="DEBUG",
            log_format="json",
            correlation_enabled=True,
        )
        # Replace handler's stream for capture
        root = logging.getLogger()
        root.handlers[0].stream = stream

        logger = logging.getLogger("test.json")
        logger.info("hello json")

        output = stream.getvalue().strip()
        lines = output.split("\n")
        # At least the "hello json" line
        json_line = next(
            (l for l in lines if "hello json" in l), None
        )
        assert json_line is not None
        parsed = json.loads(json_line)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello json"
        assert "timestamp" in parsed


# ---------------------------------------------------------------------------
# Task 3.5: Correlation ID in log output
# ---------------------------------------------------------------------------
class TestCorrelationInLogs:
    """Verify correlation ID appears in log entries during request."""

    def test_correlation_id_in_response_body(self):
        setup_logging(
            service_name="test-corr",
            log_level="INFO",
            log_format="text",
            correlation_enabled=True,
        )
        app = _make_app(correlation=True)
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        rid = response.json()["request_id"]
        # Should be a 12-char hex ID
        assert len(rid) == 12
        assert rid != "-"


# ---------------------------------------------------------------------------
# Task 3.6: X-Request-ID response header
# ---------------------------------------------------------------------------
class TestXRequestIdHeader:
    """Verify X-Request-ID header in HTTP responses."""

    def test_header_present(self):
        app = _make_app(correlation=True)
        client = TestClient(app)
        response = client.get("/test")
        assert "X-Request-ID" in response.headers

    def test_header_matches_body(self):
        app = _make_app(correlation=True)
        client = TestClient(app)
        response = client.get("/test")
        header_id = response.headers["X-Request-ID"]
        body_id = response.json()["request_id"]
        assert header_id == body_id

    def test_custom_header_propagated(self):
        app = _make_app(correlation=True)
        client = TestClient(app)
        response = client.get("/test", headers={"X-Request-ID": "my-trace-123"})
        assert response.headers["X-Request-ID"] == "my-trace-123"
        assert response.json()["request_id"] == "my-trace-123"

    def test_no_header_without_middleware(self):
        app = _make_app(correlation=False)
        client = TestClient(app)
        response = client.get("/test")
        assert "X-Request-ID" not in response.headers
