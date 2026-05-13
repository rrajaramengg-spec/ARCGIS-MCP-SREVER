"""Unit tests for exception hierarchy and ErrorResponse model (core/exceptions.py)."""

import json

import pytest
from pydantic import ValidationError

from core.exceptions import (
    ErrorResponse,
    MapGPTError,
    QueryPlanError,
    RAGContextError,
    ToolCallError,
)


class TestMapGPTError:
    """Tests for the base MapGPTError class."""

    def test_default_attributes(self):
        err = MapGPTError("something went wrong")
        assert err.message == "something went wrong"
        assert err.code == "INTERNAL_ERROR"
        assert err.status_code == 500
        assert str(err) == "something went wrong"

    def test_custom_code_and_status(self):
        err = MapGPTError("bad request", code="CUSTOM", status_code=400)
        assert err.code == "CUSTOM"
        assert err.status_code == 400

    def test_inherits_from_exception(self):
        assert issubclass(MapGPTError, Exception)


class TestQueryPlanError:
    """Tests for QueryPlanError."""

    def test_defaults(self):
        err = QueryPlanError("invalid plan")
        assert err.code == "QUERY_PLAN_ERROR"
        assert err.status_code == 400
        assert err.message == "invalid plan"

    def test_inherits_from_mapgpt_error(self):
        assert issubclass(QueryPlanError, MapGPTError)


class TestToolCallError:
    """Tests for ToolCallError."""

    def test_defaults(self):
        err = ToolCallError("tool failed")
        assert err.code == "TOOL_CALL_ERROR"
        assert err.status_code == 502
        assert err.tool_name == ""

    def test_with_tool_name(self):
        err = ToolCallError("query_features timeout", tool_name="query_features")
        assert err.tool_name == "query_features"
        assert err.message == "query_features timeout"

    def test_inherits_from_mapgpt_error(self):
        assert issubclass(ToolCallError, MapGPTError)


class TestRAGContextError:
    """Tests for RAGContextError."""

    def test_defaults(self):
        err = RAGContextError("embedding failed")
        assert err.code == "RAG_CONTEXT_ERROR"
        assert err.status_code == 500

    def test_inherits_from_mapgpt_error(self):
        assert issubclass(RAGContextError, MapGPTError)


class TestErrorResponse:
    """Tests for ErrorResponse Pydantic model."""

    def test_required_fields(self):
        resp = ErrorResponse(error="test error", code="TEST")
        assert resp.error == "test error"
        assert resp.code == "TEST"
        assert resp.service == "mcp-mapgpt-client"
        assert resp.detail is None
        assert resp.timestamp  # auto-generated

    def test_serialization_flat_json(self):
        resp = ErrorResponse(error="fail", code="X", detail="extra info")
        data = resp.model_dump()
        assert isinstance(data, dict)
        assert data["error"] == "fail"
        assert data["code"] == "X"
        assert data["detail"] == "extra info"
        assert "timestamp" in data
        assert "service" in data
        # Flat — no nested dicts
        for v in data.values():
            assert not isinstance(v, dict)

    def test_exclude_none(self):
        resp = ErrorResponse(error="fail", code="X")
        data = resp.model_dump(exclude_none=True)
        assert "detail" not in data

    def test_timestamp_is_iso8601(self):
        resp = ErrorResponse(error="x", code="X")
        # Should parse as ISO 8601 — contains T and timezone info
        assert "T" in resp.timestamp

    def test_validation_error_on_missing_fields(self):
        with pytest.raises(ValidationError):
            ErrorResponse()  # type: ignore[call-arg]
