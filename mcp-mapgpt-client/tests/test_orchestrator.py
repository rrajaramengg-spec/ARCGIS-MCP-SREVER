"""
Unit tests for the modular orchestrator architecture:
- Handler registry (@register_handler)
- BaseHandler.run_tool_loop()
- Dispatcher prefix routing
- Explicit DI verification
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.llm_service import LLMResponse, ToolCallResult


# ---------------------------------------------------------------------------
# 6.3: Handler Registry
# ---------------------------------------------------------------------------


class TestHandlerRegistry:
    """Tests for @register_handler and _HANDLER_REGISTRY."""

    def test_all_handlers_registered(self):
        from core.orchestrator.base import _HANDLER_REGISTRY

        expected = {"query", "locate", "summarize", "summarize_stat", "arcgis_execute", "execute_llm"}
        assert set(_HANDLER_REGISTRY.keys()) == expected

    def test_prefix_metadata(self):
        from core.orchestrator.base import _HANDLER_REGISTRY

        assert _HANDLER_REGISTRY["locate"]["prefix"] == "/locate "
        assert _HANDLER_REGISTRY["summarize"]["prefix"] == "/summarize "
        assert _HANDLER_REGISTRY["summarize_stat"]["prefix"] == "/summarize-stat "
        assert _HANDLER_REGISTRY["arcgis_execute"]["prefix"] == "/arcgis-execute "
        assert _HANDLER_REGISTRY["execute_llm"]["prefix"] == "/execute-llm "
        assert _HANDLER_REGISTRY["query"]["prefix"] is None

    def test_duplicate_registration_raises(self):
        from core.orchestrator.base import _HANDLER_REGISTRY, register_handler

        # Temporarily register, then clean up
        with pytest.raises(ValueError, match="Duplicate handler"):
            @register_handler("locate")
            class FakeHandler:
                pass

    def test_registry_cls_is_class(self):
        from core.orchestrator.base import _HANDLER_REGISTRY

        for name, meta in _HANDLER_REGISTRY.items():
            assert isinstance(meta["cls"], type), f"{name} cls is not a type"


# ---------------------------------------------------------------------------
# 6.4: BaseHandler.run_tool_loop()
# ---------------------------------------------------------------------------


class TestRunToolLoop:
    """Tests for BaseHandler.run_tool_loop()."""

    @pytest.mark.asyncio
    async def test_single_iteration(self):
        from core.orchestrator.base import BaseHandler

        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={"result": "ok"})

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(tool_calls=[
                ToolCallResult(tool_call_id="tc1", tool_name="geocode",
                               tool_input={"address": "test"})
            ]),
            LLMResponse(content="Done"),
        ])

        handler = BaseHandler(mock_mcp, mock_llm)
        result = await handler.run_tool_loop(
            [{"role": "user", "content": "test"}], tools=[], max_iterations=10
        )

        assert result.iterations == 1
        assert result.tool_name == "geocode"
        assert result.tool_args == {"address": "test"}
        assert result.tool_result == {"result": "ok"}
        assert result.response.content == "Done"
        assert result.llm_ms > 0
        assert result.tool_ms > 0

    @pytest.mark.asyncio
    async def test_multi_iteration_chain(self):
        from core.orchestrator.base import BaseHandler

        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={"data": "found"})

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(tool_calls=[
                ToolCallResult(tool_call_id="tc1", tool_name="search_content",
                               tool_input={"query": "parks"})
            ]),
            LLMResponse(tool_calls=[
                ToolCallResult(tool_call_id="tc2", tool_name="query_features",
                               tool_input={"layer_url": "http://x"})
            ]),
            LLMResponse(content="Found parks"),
        ])

        handler = BaseHandler(mock_mcp, mock_llm)
        result = await handler.run_tool_loop(
            [{"role": "user", "content": "find parks"}], tools=[]
        )

        assert result.iterations == 2
        assert result.tool_name == "query_features"  # last tool
        assert mock_mcp.call_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_max_iterations_cap(self):
        from core.orchestrator.base import BaseHandler
        from core.exceptions import QueryPlanError

        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={})

        tool_response = LLMResponse(tool_calls=[
            ToolCallResult(tool_call_id="tc", tool_name="search_content",
                           tool_input={"query": "x"})
        ])
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=tool_response)

        handler = BaseHandler(mock_mcp, mock_llm)
        with pytest.raises(QueryPlanError, match="exceeded 3 iterations"):
            await handler.run_tool_loop(
                [{"role": "user", "content": "loop"}], tools=[], max_iterations=3
            )

    @pytest.mark.asyncio
    async def test_tool_failure_captured(self):
        from core.orchestrator.base import BaseHandler

        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(side_effect=Exception("Timeout"))

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(tool_calls=[
                ToolCallResult(tool_call_id="tc1", tool_name="query_features",
                               tool_input={"url": "bad"})
            ]),
            LLMResponse(content="Error occurred"),
        ])

        handler = BaseHandler(mock_mcp, mock_llm)
        result = await handler.run_tool_loop(
            [{"role": "user", "content": "test"}], tools=[]
        )

        assert result.tool_result == {"error": "Timeout"}
        assert result.iterations == 1

    @pytest.mark.asyncio
    async def test_no_tool_calls_zero_iterations(self):
        from core.orchestrator.base import BaseHandler

        mock_mcp = MagicMock()
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=LLMResponse(content="Hello"))

        handler = BaseHandler(mock_mcp, mock_llm)
        result = await handler.run_tool_loop(
            [{"role": "user", "content": "hi"}], tools=[]
        )

        assert result.iterations == 0
        assert result.tool_name is None
        assert result.response.content == "Hello"


# ---------------------------------------------------------------------------
# 6.5: Dispatcher prefix routing
# ---------------------------------------------------------------------------


class TestDispatcherRouting:
    """Tests for execute() prefix routing in MapGPTOrchestrator."""

    def _make_orchestrator(self):
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock()
        mock_mcp.is_connected = True
        mock_mcp.call_tool = AsyncMock(return_value={
            "candidates": [{"address": "X", "location": {"x": 0, "y": 0}, "score": 100}]
        })
        mock_mcp.list_tools = AsyncMock(return_value=[])

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content=json.dumps({"action": "message", "message": "ok"})
        ))

        return MapGPTOrchestrator(mock_mcp, mock_llm), mock_mcp, mock_llm

    def test_prefix_routes_sorted_by_length(self):
        orch, _, _ = self._make_orchestrator()
        prefixes = [p for p, _, _ in orch._prefix_routes]
        lengths = [len(p) for p in prefixes]
        assert lengths == sorted(lengths, reverse=True)

    def test_summarize_stat_before_summarize(self):
        """'/summarize-stat ' must match before '/summarize '."""
        orch, _, _ = self._make_orchestrator()
        prefixes = [p for p, _, _ in orch._prefix_routes]
        stat_idx = prefixes.index("/summarize-stat ")
        sum_idx = prefixes.index("/summarize ")
        assert stat_idx < sum_idx

    @pytest.mark.asyncio
    async def test_locate_prefix_routes_correctly(self):
        orch, mock_mcp, _ = self._make_orchestrator()
        result = await orch.execute("/locate 123 Main St")
        assert result["action"] == "locate"
        mock_mcp.call_tool.assert_called_once_with("geocode", {"address": "123 Main St"})


# ---------------------------------------------------------------------------
# 6.6: Explicit DI verification
# ---------------------------------------------------------------------------


class TestExplicitDI:
    """Verify each handler receives only its declared dependencies."""

    def test_query_handler_has_prompts_and_cache(self):
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock()
        mock_llm = MagicMock()
        orch = MapGPTOrchestrator(mock_mcp, mock_llm)

        qh = orch._handlers["query"]
        assert hasattr(qh, "_prompts")
        assert hasattr(qh, "_tools_cache")
        assert qh._mcp is mock_mcp
        assert qh._llm is mock_llm

    def test_locate_handler_minimal_di(self):
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock()
        mock_llm = MagicMock()
        orch = MapGPTOrchestrator(mock_mcp, mock_llm)

        lh = orch._handlers["locate"]
        assert lh._mcp is mock_mcp
        assert lh._llm is mock_llm
        assert not hasattr(lh, "_prompts")
        assert not hasattr(lh, "_tools_cache")

    def test_shared_tools_cache_reference(self):
        """QueryHandler and ArcgisExecuteHandler share the same tools_cache list."""
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock()
        mock_llm = MagicMock()
        orch = MapGPTOrchestrator(mock_mcp, mock_llm)

        qh = orch._handlers["query"]
        ah = orch._handlers["arcgis_execute"]
        assert qh._tools_cache is ah._tools_cache


# ---------------------------------------------------------------------------
# Helpers: build_response, build_timing, extract_json
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for BaseHandler helper methods."""

    def test_build_response_shape(self):
        from core.orchestrator.base import BaseHandler

        resp = BaseHandler.build_response(
            action="query", message="ok", data={"x": 1},
            tool_name="query_features", tool_args={"url": "http://x"},
            execution_time_ms=100.0,
        )
        assert resp["action"] == "query"
        assert resp["execution_time_ms"] == 100.0
        assert resp["timing"] is None

    def test_build_timing_computes_total(self):
        from core.orchestrator.base import BaseHandler

        t = BaseHandler.build_timing(rag_ms=100, llm_ms=200, tool_ms=50)
        assert t["total_ms"] == 350.0
        assert t["rag_ms"] == 100.0

    def test_extract_json_plain(self):
        from core.orchestrator.base import extract_json

        result = extract_json('{"action": "query"}')
        assert result == {"action": "query"}

    def test_extract_json_markdown_fence(self):
        from core.orchestrator.base import extract_json

        result = extract_json('```json\n{"action": "locate"}\n```')
        assert result == {"action": "locate"}

    def test_extract_json_invalid_raises(self):
        from core.orchestrator.base import extract_json

        with pytest.raises(json.JSONDecodeError):
            extract_json("not json at all")
