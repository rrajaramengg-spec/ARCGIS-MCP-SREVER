"""Tests for tools/_base.py — error model, utilities, and error-handling wrapper."""

import json
import pytest

from mcp_arcgis_server.tools._base import (
    FIELD_NOT_FOUND,
    INTERNAL_ERROR,
    INVALID_INPUT,
    ToolError,
    ToolExecutionError,
    _wrap_with_error_handling,
    cap_result_count,
    format_features,
    parse_geometry_input,
    resolve_field_name,
)


# ── ToolError model ─────────────────────────────────────────────────────


class TestToolError:
    def test_model_fields(self):
        err = ToolError(
            error="something failed",
            error_code="TEST_ERROR",
            detail="details here",
            tool_name="test_tool",
        )
        assert err.error == "something failed"
        assert err.error_code == "TEST_ERROR"
        assert err.detail == "details here"
        assert err.tool_name == "test_tool"
        assert err.retry_safe is False

    def test_retry_safe_default_false(self):
        err = ToolError(
            error="e",
            error_code="E",
            detail="d",
            tool_name="t",
        )
        assert err.retry_safe is False

    def test_model_dump(self):
        err = ToolError(
            error="e",
            error_code="E",
            detail="d",
            tool_name="t",
            retry_safe=True,
        )
        d = err.model_dump()
        assert d["retry_safe"] is True
        assert set(d.keys()) == {"error", "error_code", "detail", "tool_name", "retry_safe"}


# ── ToolExecutionError exception ─────────────────────────────────────────


class TestToolExecutionError:
    def test_attributes(self):
        exc = ToolExecutionError(
            error="bad input",
            error_code=INVALID_INPUT,
            detail="field missing",
            retry_safe=True,
        )
        assert str(exc) == "bad input"
        assert exc.error_code == INVALID_INPUT
        assert exc.detail == "field missing"
        assert exc.retry_safe is True

    def test_retry_safe_default_false(self):
        exc = ToolExecutionError(
            error="e",
            error_code="E",
            detail="d",
        )
        assert exc.retry_safe is False


# ── parse_geometry_input ─────────────────────────────────────────────────


class TestParseGeometryInput:
    def test_valid_arcgis_point(self):
        geom = parse_geometry_input('{"x": 1, "y": 2}')
        assert geom == {"x": 1, "y": 2}

    def test_geojson_point_normalized(self):
        geojson = json.dumps({"type": "Point", "coordinates": [10.0, 20.0]})
        result = parse_geometry_input(geojson)
        assert result["x"] == 10.0
        assert result["y"] == 20.0
        assert "spatialReference" in result

    def test_empty_string_raises(self):
        with pytest.raises(ToolExecutionError) as exc_info:
            parse_geometry_input("")
        assert exc_info.value.error_code == INVALID_INPUT

    def test_none_raises(self):
        with pytest.raises(ToolExecutionError) as exc_info:
            parse_geometry_input(None)
        assert exc_info.value.error_code == INVALID_INPUT

    def test_invalid_json_raises(self):
        with pytest.raises(ToolExecutionError) as exc_info:
            parse_geometry_input("{not valid json}")
        assert exc_info.value.error_code == INVALID_INPUT


# ── resolve_field_name ───────────────────────────────────────────────────


class TestResolveFieldName:
    FIELDS = [
        {"name": "ObjectID"},
        {"name": "Population"},
        {"name": "City_Name"},
    ]

    def test_exact_match(self):
        assert resolve_field_name(self.FIELDS, "Population") == "Population"

    def test_case_insensitive(self):
        assert resolve_field_name(self.FIELDS, "population") == "Population"
        assert resolve_field_name(self.FIELDS, "CITY_NAME") == "City_Name"

    def test_not_found_raises(self):
        with pytest.raises(ToolExecutionError) as exc_info:
            resolve_field_name(self.FIELDS, "nonexistent")
        assert exc_info.value.error_code == FIELD_NOT_FOUND
        assert "nonexistent" in exc_info.value.detail


# ── cap_result_count ─────────────────────────────────────────────────────


class TestCapResultCount:
    def test_none_returns_max(self):
        assert cap_result_count(None, 200) == 200

    def test_below_max(self):
        assert cap_result_count(50, 200) == 50

    def test_above_max_capped(self):
        assert cap_result_count(500, 200) == 200

    def test_equal_to_max(self):
        assert cap_result_count(200, 200) == 200


# ── format_features ──────────────────────────────────────────────────────


class TestFormatFeatures:
    FEATURES = [
        {"attributes": {"name": "a", "pop": 100}},
        {"attributes": {"name": "b", "pop": 200}},
    ]

    def test_all_fields(self):
        result = format_features(self.FEATURES)
        assert len(result) == 2
        assert result[0] == {"name": "a", "pop": 100}

    def test_specific_fields(self):
        result = format_features(self.FEATURES, fields=["name"])
        assert result[0] == {"name": "a"}
        assert result[1] == {"name": "b"}

    def test_empty_list(self):
        assert format_features([]) == []


# ── _wrap_with_error_handling ────────────────────────────────────────────


class TestWrapWithErrorHandling:
    @pytest.mark.asyncio
    async def test_success_passthrough(self):
        async def my_tool():
            return {"result": "ok"}

        wrapped = _wrap_with_error_handling(my_tool, "my_tool")
        result = await wrapped()
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_tool_execution_error_caught(self):
        async def failing_tool():
            raise ToolExecutionError(
                error="bad",
                error_code=INVALID_INPUT,
                detail="detail",
                retry_safe=True,
            )

        wrapped = _wrap_with_error_handling(failing_tool, "failing_tool")
        result = await wrapped()
        assert result["error"] == "bad"
        assert result["error_code"] == INVALID_INPUT
        assert result["tool_name"] == "failing_tool"
        assert result["retry_safe"] is True

    @pytest.mark.asyncio
    async def test_unexpected_exception_caught(self):
        async def crasher():
            raise RuntimeError("boom")

        wrapped = _wrap_with_error_handling(crasher, "crasher")
        result = await wrapped()
        assert result["error_code"] == INTERNAL_ERROR
        assert result["tool_name"] == "crasher"
        assert "boom" in result["detail"]
        assert result["retry_safe"] is False

    @pytest.mark.asyncio
    async def test_wrapper_preserves_name(self):
        async def original_tool():
            pass

        wrapped = _wrap_with_error_handling(original_tool, "original_tool")
        assert wrapped.__name__ == "original_tool"
