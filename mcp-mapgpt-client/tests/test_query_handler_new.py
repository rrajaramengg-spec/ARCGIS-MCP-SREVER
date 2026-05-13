"""
Unit tests for new QueryHandler methods:
- _resolve_location()
- _wrap_query_result()
- _execute_analyze()
- _execute_locate() with children / array format
- _validate_plan() extended for analyze, locate-children, join_type
"""

import json
import time

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.llm_service import LLMService
from core.mcp_client import MCPClient
from core.orchestrator.query_handler import QueryHandler


def _make_handler(call_tool_return=None, call_tool_side_effect=None):
    """Create a QueryHandler with mocked MCP and LLM."""
    mock_mcp = MagicMock(spec=MCPClient)
    mock_mcp.is_connected = True
    if call_tool_side_effect:
        mock_mcp.call_tool = AsyncMock(side_effect=call_tool_side_effect)
    else:
        mock_mcp.call_tool = AsyncMock(
            return_value=call_tool_return or {}
        )
    mock_llm = MagicMock(spec=LLMService)
    handler = QueryHandler(
        mcp=mock_mcp, llm=mock_llm, prompts={"query_instructions": {"system": "You are a test assistant.", "human": "{context}\n{query}"}}, tools_cache=[]
    )
    handler._progress_callback = None
    return handler


# ── _resolve_location ─────────────────────────────


class TestResolveLocation:
    """Tests for _resolve_location()."""

    @pytest.mark.asyncio
    async def test_address_geocode(self):
        handler = _make_handler(call_tool_return={
            "candidates": [
                {
                    "address": "20 Church Rd",
                    "location": {"x": -74.98, "y": 39.93},
                    "score": 97.5,
                }
            ],
            "count": 1,
        })
        node = {"type": "address", "address": "20 Church Rd"}
        result = await handler._resolve_location(node)

        assert result["geometry"]["x"] == -74.98
        assert result["geometry"]["y"] == 39.93
        assert result["geometry"]["spatialReference"]["wkid"] == 4326
        assert result["source"]["type"] == "geocode"
        assert result["source"]["address"] == "20 Church Rd"
        assert result["source"]["score"] == 97.5
        handler._mcp.call_tool.assert_called_once_with(
            "geocode", {"address": "20 Church Rd"}
        )

    @pytest.mark.asyncio
    async def test_address_no_candidates_raises(self):
        handler = _make_handler(
            call_tool_return={"candidates": [], "count": 0}
        )
        node = {"type": "address", "address": "nonexistent"}
        with pytest.raises(ValueError, match="no candidates"):
            await handler._resolve_location(node)

    @pytest.mark.asyncio
    async def test_coordinates_no_reverse_geocode(self):
        """Location type returns x,y directly — NO reverse geocode call."""
        handler = _make_handler()
        node = {"type": "location", "lon": -74.98, "lat": 39.93}
        result = await handler._resolve_location(node)

        assert result["geometry"]["x"] == -74.98
        assert result["geometry"]["y"] == 39.93
        assert result["source"]["type"] == "coordinates"
        # Must NOT call any MCP tool
        handler._mcp.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_coordinates_alt_keys(self):
        handler = _make_handler()
        node = {"type": "location", "longitude": -105.0, "latitude": 40.0}
        result = await handler._resolve_location(node)
        assert result["geometry"]["x"] == -105.0
        assert result["geometry"]["y"] == 40.0

    @pytest.mark.asyncio
    async def test_coordinates_missing_raises(self):
        handler = _make_handler()
        node = {"type": "location", "lon": -74.98}
        with pytest.raises(ValueError, match="missing lon/lat"):
            await handler._resolve_location(node)

    @pytest.mark.asyncio
    async def test_where_query_geometry(self):
        handler = _make_handler(call_tool_return={
            "features": [
                {
                    "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                    "attributes": {"NAME": "Burlington"},
                }
            ],
            "count": 1,
        })
        node = {
            "type": "where",
            "layer": "COUNTY",
            "layer_url": "https://x/0",
            "where": "NAME='Burlington'",
        }
        result = await handler._resolve_location(node)

        assert "rings" in result["geometry"]
        assert result["source"]["type"] == "feature_query"
        assert result["source"]["layer"] == "COUNTY"
        assert len(result["source"]["features"]) == 1
        handler._mcp.call_tool.assert_called_once_with(
            "query_features",
            {
                "layer_url": "https://x/0",
                "where": "NAME='Burlington'",
                "return_geometry": True,
            },
        )

    @pytest.mark.asyncio
    async def test_where_no_features_raises(self):
        handler = _make_handler(
            call_tool_return={"features": [], "count": 0}
        )
        node = {
            "type": "where",
            "layer": "COUNTY",
            "layer_url": "https://x/0",
            "where": "NAME='ZZZ'",
        }
        with pytest.raises(ValueError, match="no features"):
            await handler._resolve_location(node)

    @pytest.mark.asyncio
    async def test_fallback_old_dict_with_address(self):
        handler = _make_handler(call_tool_return={
            "candidates": [
                {"location": {"x": -75, "y": 40}, "score": 90}
            ],
        })
        node = {"address": "123 Main"}  # no type field
        result = await handler._resolve_location(node)
        assert result["source"]["type"] == "geocode"
        handler._mcp.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_old_dict_with_coords(self):
        handler = _make_handler()
        node = {"latitude": 39.7, "longitude": -105.0}  # no type
        result = await handler._resolve_location(node)
        assert result["geometry"]["x"] == -105.0
        assert result["geometry"]["y"] == 39.7
        handler._mcp.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_type_raises(self):
        handler = _make_handler()
        node = {"type": "magic"}
        with pytest.raises(ValueError, match="Unknown root node type"):
            await handler._resolve_location(node)


# ── _wrap_query_result ─────────────────────────────


class TestWrapQueryResult:
    """Tests for _wrap_query_result()."""

    def _handler(self):
        return _make_handler()

    def test_flat_where(self):
        h = self._handler()
        data = {
            "layer": "ASSET",
            "layer_url": "https://x/0",
            "type": "where",
            "features": [{"attributes": {"ID": 1}}],
            "count": 1,
            "geometryType": "esriGeometryPoint",
            "fields": [{"name": "ID"}],
            "spatialReference": {"wkid": 4326},
        }
        result = h._wrap_query_result(data)
        assert result["source"] is None
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert r["layer"] == "ASSET"
        assert r["features"] == [{"attributes": {"ID": 1}}]
        assert r["geometryType"] == "esriGeometryPoint"

    def test_spatial_join(self):
        h = self._handler()
        data = {
            "layer": "COUNTY",
            "layer_url": "https://x/6",
            "type": "spatial_join",
            "parent": {
                "features": [{"attributes": {"NAME": "Adams"}}],
                "geometry": {"rings": [[]]},
            },
            "children": [
                {"layer": "CUST", "features": [{"attributes": {"ID": 1}}]},
            ],
        }
        result = h._wrap_query_result(data)
        assert result["source"]["type"] == "feature_query"
        assert len(result["source"]["features"]) == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["layer"] == "CUST"

    def test_count_only(self):
        h = self._handler()
        data = {
            "layer": "PLACES",
            "layer_url": "https://x/1",
            "type": "count",
            "count": 42,
        }
        result = h._wrap_query_result(data)
        assert result["source"] is None
        assert result["results"][0]["count"] == 42
        assert result["results"][0]["type"] == "count"

    def test_multi_result(self):
        h = self._handler()
        data = {
            "results": [
                {
                    "layer": "A",
                    "type": "where",
                    "features": [{"attributes": {"ID": 1}}],
                    "count": 1,
                },
                {
                    "layer": "B",
                    "type": "count",
                    "count": 10,
                },
            ],
            "count": 2,
        }
        result = h._wrap_query_result(data)
        assert result["source"] is None
        assert len(result["results"]) == 2

    def test_error_passthrough(self):
        h = self._handler()
        data = {"error": "Execution failed", "detail": "timeout"}
        result = h._wrap_query_result(data)
        assert result["error"] == "Execution failed: timeout"
        assert result["results"] == []

    def test_non_dict_input(self):
        h = self._handler()
        result = h._wrap_query_result("not a dict")
        assert result == {"source": None, "results": []}

    def test_none_input(self):
        h = self._handler()
        result = h._wrap_query_result(None)
        assert result == {"source": None, "results": []}


# ── Graph-only pipeline (Phase 3) ─────────────────


class TestGraphOnlyPipeline:
    """Tests for the graph-only execute() pipeline."""

    @pytest.mark.asyncio
    async def test_message_action_skips_graph(self):
        """Action='message' returns immediately without graph execution."""
        handler = _make_handler()
        handler._rag_service = None

        message_plan = {"action": "message", "message": "Hello there"}
        llm_resp = MagicMock()
        llm_resp.content = json.dumps(message_plan)
        llm_resp.tool_calls = []
        llm_resp.has_tool_calls = False
        handler._llm.complete = AsyncMock(return_value=llm_resp)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "core.orchestrator.query_handler.build_rag_context",
                AsyncMock(return_value=("ctx", [])),
            )
            mp.setattr(
                "core.orchestrator.query_handler.ResponseCache",
                MagicMock(get=AsyncMock(return_value=None)),
            )
            result = await handler.execute("hello")

        assert result["action"] == "message"
        assert result["message"] == "Hello there"
        # MCP should NOT have been called (no graph execution)
        handler._mcp.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_action_routes_through_graph(self):
        """Action='query' invokes _execute_via_graph."""
        handler = _make_handler(call_tool_return={
            "features": [{"attributes": {"NAME": "Test"}}],
            "count": 1,
        })
        handler._rag_service = None
        handler._config = MagicMock()
        handler._config.node_retry_budget = 3
        handler._config.arcgis_max_concurrent = 5
        handler._config.circuit_breaker_threshold = 5

        plan = {
            "action": "query",
            "message": "Found features",
            "query": [{
                "node_id": "q1",
                "intent": "find features",
                "type": "where",
                "layer": "PSAP",
                "layer_url": "https://example.com/0",
                "where": "1=1",
            }],
        }
        llm_resp = MagicMock()
        llm_resp.content = json.dumps(plan)
        llm_resp.tool_calls = []
        llm_resp.has_tool_calls = False
        handler._llm.complete = AsyncMock(return_value=llm_resp)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "core.orchestrator.query_handler.build_rag_context",
                AsyncMock(return_value=("ctx", [])),
            )
            mp.setattr(
                "core.orchestrator.query_handler.ResponseCache",
                MagicMock(
                    get=AsyncMock(return_value=None),
                    set=AsyncMock(return_value=True),
                    store_query_mapping=AsyncMock(return_value=True),
                ),
            )
            mp.setattr(
                "core.orchestrator.query_handler.ConversationHistory",
                MagicMock(
                    add_message=AsyncMock(return_value=True),
                    get_turns=AsyncMock(return_value=[]),
                ),
            )
            result = await handler.execute("show psap")

        assert result["action"] == "query"
        assert "query_id" in result
        # MCP call_tool should have been invoked (graph executed)
        assert handler._mcp.call_tool.call_count >= 1


# NOTE: TestExecuteLocateWithChildren and TestExecuteAnalyze removed ---
# those methods were deleted in the graph-only pipeline rewrite (Phase 3).
# Locate and analyze actions are now executed via GraphRuntime.



class TestValidatePlanExtended:
    """Tests for extended _validate_plan()."""

    def _rag_layers(self):
        return [
            {
                "layer_name": "ASSET",
                "url": "https://correct/0",
                "fields": [
                    {"field_name": "ID"},
                    {"field_name": "NAME"},
                ],
            },
            {
                "layer_name": "COUNTY",
                "url": "https://correct/6",
                "fields": [{"field_name": "NAME"}],
            },
        ]

    def test_analyze_url_correction(self):
        handler = _make_handler()
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "X",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "buffer",
                            "children": [
                                {
                                    "type": "where",
                                    "layer": "ASSET",
                                    "layer_url": "https://wrong/0",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = handler._validate_plan(plan, self._rag_layers())
        child = result["analyze"][0]["children"][0]["children"][0]
        assert child["layer_url"] == "https://correct/0"

    def test_locate_children_url_correction(self):
        handler = _make_handler()
        plan = {
            "action": "locate",
            "locate": [
                {
                    "type": "address",
                    "address": "X",
                    "children": [
                        {
                            "layer": "COUNTY",
                            "layer_url": "https://wrong/6",
                        }
                    ],
                }
            ],
        }
        result = handler._validate_plan(plan, self._rag_layers())
        child = result["locate"][0]["children"][0]
        assert child["layer_url"] == "https://correct/6"

    def test_locate_dict_format(self):
        handler = _make_handler()
        plan = {
            "action": "locate",
            "locate": {
                "type": "address",
                "address": "X",
                "children": [
                    {"layer": "COUNTY", "layer_url": "https://wrong/6"}
                ],
            },
        }
        result = handler._validate_plan(plan, self._rag_layers())
        child = result["locate"]["children"][0]
        assert child["layer_url"] == "https://correct/6"

    def test_tool_to_join_type_auto_correction(self):
        handler = _make_handler()
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "X",
                    "children": [
                        {
                            "type": "tool",
                            "tool": "buffer",  # wrong key
                            "children": [
                                {
                                    "layer": "ASSET",
                                    "layer_url": "https://correct/0",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = handler._validate_plan(plan, self._rag_layers())
        tool_node = result["analyze"][0]["children"][0]
        assert "join_type" in tool_node
        assert tool_node["join_type"] == "buffer"
        assert "tool" not in tool_node

    def test_query_still_works(self):
        handler = _make_handler()
        plan = {
            "action": "query",
            "query": [
                {
                    "type": "where",
                    "layer": "ASSET",
                    "layer_url": "https://wrong/0",
                }
            ],
        }
        result = handler._validate_plan(plan, self._rag_layers())
        assert result["query"][0]["layer_url"] == "https://correct/0"

    def test_fill_missing_url(self):
        handler = _make_handler()
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "X",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "buffer",
                            "children": [
                                {
                                    "layer": "ASSET",
                                    # no layer_url
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = handler._validate_plan(plan, self._rag_layers())
        child = result["analyze"][0]["children"][0]["children"][0]
        assert child["layer_url"] == "https://correct/0"
