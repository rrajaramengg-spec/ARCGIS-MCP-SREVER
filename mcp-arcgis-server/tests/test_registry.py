"""Tests for tools/_registry.py — decorator, client binding, discovery."""

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest
from pydantic import Field

from mcp_arcgis_server.tools._registry import (
    ToolDefinition,
    _TOOL_REGISTRY,
    _bind_client,
    discover_and_register,
    get_registered_tools,
    register_tool,
)


# ── @register_tool decorator ────────────────────────────────────────────


class TestRegisterToolDecorator:
    def setup_method(self):
        self._saved = list(_TOOL_REGISTRY)
        _TOOL_REGISTRY.clear()

    def teardown_method(self):
        _TOOL_REGISTRY.clear()
        _TOOL_REGISTRY.extend(self._saved)

    def test_decorator_adds_to_registry(self):
        @register_tool("my_tool", "A test tool")
        async def my_tool(client, x: int = 1):
            pass

        assert len(_TOOL_REGISTRY) == 1
        assert _TOOL_REGISTRY[0].name == "my_tool"
        assert _TOOL_REGISTRY[0].description == "A test tool"
        assert _TOOL_REGISTRY[0].fn is my_tool

    def test_multiple_decorators(self):
        @register_tool("tool_a", "Tool A")
        async def tool_a(client):
            pass

        @register_tool("tool_b", "Tool B")
        async def tool_b(client):
            pass

        assert len(_TOOL_REGISTRY) == 2
        names = [t.name for t in _TOOL_REGISTRY]
        assert "tool_a" in names
        assert "tool_b" in names

    def test_get_registered_tools_returns_copy(self):
        @register_tool("t", "T")
        async def t(client):
            pass

        tools = get_registered_tools()
        assert len(tools) == 1
        tools.clear()
        assert len(get_registered_tools()) == 1  # Original unaffected


# ── _bind_client ─────────────────────────────────────────────────────────


class TestBindClient:
    def test_removes_client_from_signature(self):
        async def my_fn(client, x: int, y: str = "hello"):
            pass

        mock_client = MagicMock()
        bound = _bind_client(my_fn, mock_client)
        sig = inspect.signature(bound)
        assert "client" not in sig.parameters
        assert "x" in sig.parameters
        assert "y" in sig.parameters

    def test_preserves_name_and_doc(self):
        async def my_fn(client):
            """Some docstring."""
            pass

        bound = _bind_client(my_fn, MagicMock())
        assert bound.__name__ == "my_fn"
        assert bound.__doc__ == "Some docstring."

    def test_async_detection_preserved(self):
        async def my_fn(client):
            pass

        bound = _bind_client(my_fn, MagicMock())
        assert asyncio.iscoroutinefunction(bound)

    @pytest.mark.asyncio
    async def test_client_is_passed_through(self):
        async def my_fn(client, x: int = 5):
            return {"client": client, "x": x}

        sentinel = object()
        bound = _bind_client(my_fn, sentinel)
        result = await bound(x=10)
        assert result["client"] is sentinel
        assert result["x"] == 10

    def test_pydantic_field_annotations_preserved(self):
        async def my_fn(
            client,
            layer_url: str = Field(description="The URL"),
            count: int = Field(default=10, description="Max count"),
        ):
            pass

        bound = _bind_client(my_fn, MagicMock())
        sig = inspect.signature(bound)
        layer_param = sig.parameters["layer_url"]
        assert layer_param.default.description == "The URL"
        count_param = sig.parameters["count"]
        assert count_param.default.default == 10


# ── discover_and_register ───────────────────────────────────────────────


class TestDiscoverAndRegister:
    def setup_method(self):
        self._saved = list(_TOOL_REGISTRY)
        _TOOL_REGISTRY.clear()

    def teardown_method(self):
        _TOOL_REGISTRY.clear()
        _TOOL_REGISTRY.extend(self._saved)

    def test_registers_tools_on_mcp(self):
        @register_tool("test_tool_a", "Tool A desc")
        async def test_tool_a(client, x: int = 1):
            return x

        mock_mcp = MagicMock(spec=["add_tool"])
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.disabled_tools_list = []

        with patch(
            "mcp_arcgis_server.tools._registry._auto_import_tool_modules"
        ):
            count = discover_and_register(mock_mcp, mock_client, mock_config)

        assert count == 1
        mock_mcp.add_tool.assert_called_once()
        call_kwargs = mock_mcp.add_tool.call_args
        assert call_kwargs.kwargs["name"] == "test_tool_a"
        assert call_kwargs.kwargs["description"] == "Tool A desc"

    def test_disabled_tools_skipped(self):
        @register_tool("enabled_tool", "Enabled")
        async def enabled_tool(client):
            pass

        @register_tool("disabled_tool", "Disabled")
        async def disabled_tool(client):
            pass

        mock_mcp = MagicMock(spec=["add_tool"])
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.disabled_tools_list = ["disabled_tool"]

        with patch(
            "mcp_arcgis_server.tools._registry._auto_import_tool_modules"
        ):
            count = discover_and_register(mock_mcp, mock_client, mock_config)

        assert count == 1
        call_kwargs = mock_mcp.add_tool.call_args
        assert call_kwargs.kwargs["name"] == "enabled_tool"


# ── _bind_client end-to-end with func_metadata ──────────────────────────


class TestBindClientEndToEnd:
    """Verify _bind_client produces a valid MCP tool schema via func_metadata."""

    def test_bound_function_produces_valid_schema(self):
        """Partial + signature rewrite produces JSON schema without 'client' param."""
        from typing import Annotated
        from mcp.server.fastmcp.utilities.func_metadata import func_metadata

        async def sample_tool(
            client,
            layer_url: Annotated[str, Field(description="Layer URL")],
            where: Annotated[str, Field(description="SQL filter")] = "1=1",
            max_results: Annotated[int, Field(description="Max results")] = 100,
        ) -> dict:
            """A sample tool."""
            pass

        mock_client = MagicMock()
        bound = _bind_client(sample_tool, mock_client)

        meta = func_metadata(bound)
        schema = meta.arg_model.model_json_schema()

        # 'client' should NOT appear in the schema
        assert "client" not in schema.get("properties", {}), (
            "'client' should be excluded from the schema"
        )
        # Expected params should appear
        assert "layer_url" in schema["properties"]
        assert "where" in schema["properties"]
        assert "max_results" in schema["properties"]
        # Required should only include layer_url (others have defaults)
        assert "layer_url" in schema.get("required", [])
        assert "where" not in schema.get("required", [])
        assert "max_results" not in schema.get("required", [])

    @pytest.mark.asyncio
    async def test_bound_function_callable_with_correct_args(self):
        """Bound function is callable and passes client correctly."""

        async def sample_tool(client, value: int = 5) -> int:
            return value * 2

        mock_client = MagicMock()
        bound = _bind_client(sample_tool, mock_client)

        # Should be callable without client arg
        result = await bound(value=10)
        assert result == 20
