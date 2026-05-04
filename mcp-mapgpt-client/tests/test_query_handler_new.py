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
        mcp=mock_mcp, llm=mock_llm, prompts={}, tools_cache=[]
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
                    "attributes": {"NAME": "Springfield"},
                }
            ],
            "count": 1,
        })
        node = {
            "type": "where",
            "layer": "COUNTY",
            "layer_url": "https://x/0",
            "where": "NAME='Springfield'",
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
                "where": "NAME='Springfield'",
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
            "layer": "BUILDINGS",
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
        assert r["layer"] == "BUILDINGS"
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
        assert result["error"] == "Execution failed"
        assert result["results"] == []

    def test_non_dict_input(self):
        h = self._handler()
        result = h._wrap_query_result("not a dict")
        assert result == {"source": None, "results": []}

    def test_none_input(self):
        h = self._handler()
        result = h._wrap_query_result(None)
        assert result == {"source": None, "results": []}


# ── _execute_locate with children ──────────────────


class TestExecuteLocateWithChildren:
    """Tests for _execute_locate with array format and children."""

    @pytest.mark.asyncio
    async def test_array_format_single(self):
        """Array with single address node, no children."""
        handler = _make_handler(call_tool_return={
            "candidates": [
                {"location": {"x": -75, "y": 40}, "score": 95}
            ],
        })
        plan = {
            "action": "locate",
            "locate": [{"type": "address", "address": "123 Main"}],
            "message": "Locating",
        }
        result = await handler._execute_locate(plan, time.perf_counter())
        assert result["action"] == "locate"
        assert result["data"]["source"]["type"] == "geocode"
        assert result["data"]["results"] == []

    @pytest.mark.asyncio
    async def test_dict_format_backward_compat(self):
        """Legacy dict format still works."""
        handler = _make_handler(call_tool_return={
            "candidates": [
                {"location": {"x": -75, "y": 40}, "score": 95}
            ],
        })
        plan = {
            "action": "locate",
            "locate": {"type": "address", "address": "123 Main"},
            "message": "Locating",
        }
        result = await handler._execute_locate(plan, time.perf_counter())
        assert result["action"] == "locate"
        assert result["data"]["source"]["type"] == "geocode"

    @pytest.mark.asyncio
    async def test_with_children(self):
        """Address with children spatial lookup."""
        call_count = 0

        async def _side_effect(name, args, **kwargs):
            nonlocal call_count
            call_count += 1
            if name == "geocode":
                return {
                    "candidates": [
                        {"location": {"x": -75, "y": 40}, "score": 95}
                    ],
                }
            if name == "query_features":
                return {
                    "features": [
                        {"attributes": {"NAME": "Springfield"}}
                    ],
                    "count": 1,
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "locate",
            "locate": [
                {
                    "type": "address",
                    "address": "20 Church Rd",
                    "children": [
                        {
                            "type": "where",
                            "layer": "COUNTY",
                            "layer_url": "https://x/6",
                        }
                    ],
                }
            ],
            "message": "Finding county",
        }
        result = await handler._execute_locate(plan, time.perf_counter())
        assert result["data"]["source"]["type"] == "geocode"
        assert len(result["data"]["results"]) == 1
        assert result["data"]["results"][0]["layer"] == "COUNTY"
        assert result["data"]["results"][0]["join_type"] == "spatial"

    @pytest.mark.asyncio
    async def test_multiple_children(self):
        """Multiple children under one locate node."""
        async def _side_effect(name, args, **kwargs):
            if name == "geocode":
                return {
                    "candidates": [
                        {"location": {"x": -75, "y": 40}, "score": 95}
                    ],
                }
            if name == "query_features":
                layer = "UNKNOWN"
                if "COUNTY" in args.get("layer_url", ""):
                    layer = "COUNTY"
                elif "STATIONS" in args.get("layer_url", ""):
                    layer = "STATIONS"
                return {
                    "features": [{"attributes": {"NAME": layer}}],
                    "count": 1,
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "locate",
            "locate": [
                {
                    "type": "address",
                    "address": "20 Church Rd",
                    "children": [
                        {"layer": "COUNTY", "layer_url": "https://COUNTY/6"},
                        {"layer": "STATIONS", "layer_url": "https://STATIONS/7"},
                    ],
                }
            ],
            "message": "Finding county and STATIONS",
        }
        result = await handler._execute_locate(plan, time.perf_counter())
        assert len(result["data"]["results"]) == 2

    @pytest.mark.asyncio
    async def test_multiple_locate_nodes(self):
        """Two locate nodes processed in parallel."""
        async def _side_effect(name, args, **kwargs):
            if name == "geocode":
                addr = args.get("address", "")
                if "Church" in addr:
                    return {
                        "candidates": [
                            {"location": {"x": -75, "y": 40}, "score": 95}
                        ],
                    }
                return {
                    "candidates": [
                        {"location": {"x": -80, "y": 35}, "score": 90}
                    ],
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "locate",
            "locate": [
                {"type": "address", "address": "20 Church Rd"},
                {"type": "address", "address": "100 Main St"},
            ],
            "message": "Locating two addresses",
        }
        result = await handler._execute_locate(plan, time.perf_counter())
        # source should be a list of two sources
        assert isinstance(result["data"]["source"], list)
        assert len(result["data"]["source"]) == 2

    @pytest.mark.asyncio
    async def test_child_failure_doesnt_break(self):
        """One child query failure doesn't break the other."""
        call_idx = 0

        async def _side_effect(name, args, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if name == "geocode":
                return {
                    "candidates": [
                        {"location": {"x": -75, "y": 40}, "score": 95}
                    ],
                }
            if name == "query_features":
                if "BAD" in args.get("layer_url", ""):
                    raise Exception("Connection timeout")
                return {
                    "features": [{"attributes": {"NAME": "OK"}}],
                    "count": 1,
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "locate",
            "locate": [
                {
                    "type": "address",
                    "address": "20 Church Rd",
                    "children": [
                        {"layer": "BAD", "layer_url": "https://BAD/0"},
                        {"layer": "GOOD", "layer_url": "https://GOOD/1"},
                    ],
                }
            ],
            "message": "Test",
        }
        result = await handler._execute_locate(plan, time.perf_counter())
        # One child failed, one succeeded
        assert len(result["data"]["results"]) == 1
        assert result["data"]["results"][0]["layer"] == "GOOD"

    @pytest.mark.asyncio
    async def test_missing_payload(self):
        handler = _make_handler()
        plan = {"action": "locate", "message": "No locate data"}
        result = await handler._execute_locate(plan, time.perf_counter())
        assert result["action"] == "locate"
        assert result["data"] is None

    @pytest.mark.asyncio
    async def test_coordinates_no_reverse_geocode(self):
        """Coordinates locate should NOT call reverse_geocode."""
        handler = _make_handler()
        plan = {
            "action": "locate",
            "locate": [{"type": "location", "lon": -74.98, "lat": 39.93}],
            "message": "Locating coords",
        }
        result = await handler._execute_locate(plan, time.perf_counter())
        assert result["action"] == "locate"
        assert result["data"]["source"]["type"] == "coordinates"
        handler._mcp.call_tool.assert_not_called()


# ── _execute_analyze ───────────────────────────────


class TestExecuteAnalyze:
    """Tests for _execute_analyze()."""

    @pytest.mark.asyncio
    async def test_buffer_chain(self):
        """Buffer: geocode → buffer_and_query → query_features per child."""
        async def _side_effect(name, args, **kwargs):
            if name == "geocode":
                return {
                    "candidates": [
                        {"location": {"x": -75, "y": 40}, "score": 95}
                    ],
                }
            if name == "buffer_and_query":
                return {
                    "buffer_geometry": {
                        "rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]
                    },
                    "radius": 5000,
                    "unit": "meters",
                }
            if name == "query_features":
                return {
                    "features": [{"attributes": {"ID": 1}}],
                    "count": 1,
                    "geometryType": "esriGeometryPoint",
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "20 Church Rd",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "buffer",
                            "distance": 5000,
                            "unit": "meters",
                            "children": [
                                {
                                    "type": "where",
                                    "layer": "SUPPORT",
                                    "layer_url": "https://x/0",
                                }
                            ],
                        }
                    ],
                }
            ],
            "message": "Finding supports within 5km",
        }
        result = await handler._execute_analyze(plan, time.perf_counter())
        assert result["action"] == "analyze"
        assert result["data"]["source"]["type"] == "geocode"
        assert "buffer_geometry" not in result["data"]["source"]
        # First result should be the _buffer_zone entry
        bz = result["data"]["results"][0]
        assert bz["layer"] == "_buffer_zone"
        assert bz["type"] == "buffer_zone"
        assert bz["join_type"] == "buffer"
        assert bz["count"] == 1
        assert "rings" in bz["features"][0]["geometry"]
        assert bz["features"][0]["attributes"]["radius"] == 5000
        assert bz["features"][0]["attributes"]["unit"] == "meters"
        # Second result should be the child layer
        assert result["data"]["results"][1]["join_type"] == "buffer"
        assert result["data"]["results"][1]["layer"] == "SUPPORT"

    @pytest.mark.asyncio
    async def test_proximity_chain(self):
        """Proximity: geocode → find_nearby per child."""
        async def _side_effect(name, args, **kwargs):
            if name == "geocode":
                return {
                    "candidates": [
                        {"location": {"x": -75, "y": 40}, "score": 95}
                    ],
                }
            if name == "find_nearby":
                return {
                    "features": [
                        {
                            "attributes": {"ID": 1},
                            "distance": 0.5,
                            "distance_unit": "miles",
                        }
                    ],
                    "count": 1,
                    "total_in_radius": 3,
                    "search_radius": 1.0,
                    "search_unit": "miles",
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "20 Church Rd",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "proximity",
                            "distance": 1.0,
                            "unit": "miles",
                            "top": 2,
                            "children": [
                                {
                                    "type": "where",
                                    "layer": "SUPPORT",
                                    "layer_url": "https://x/0",
                                }
                            ],
                        }
                    ],
                }
            ],
            "message": "Finding nearest",
        }
        result = await handler._execute_analyze(plan, time.perf_counter())
        assert result["action"] == "analyze"
        r = result["data"]["results"][0]
        assert r["join_type"] == "proximity"
        assert r["total_in_radius"] == 3
        assert r["features"][0]["distance"] == 0.5
        # Proximity should NOT include _buffer_zone
        assert not any(
            res.get("layer") == "_buffer_zone" for res in result["data"]["results"]
        )

    @pytest.mark.asyncio
    async def test_where_root(self):
        """Root type=where queries a feature then buffers from it."""
        async def _side_effect(name, args, **kwargs):
            if name == "query_features":
                if args.get("return_geometry"):
                    return {
                        "features": [
                            {
                                "geometry": {"x": -75, "y": 40},
                                "attributes": {"ID": 123},
                            }
                        ],
                        "count": 1,
                    }
                # Spatial filter query
                return {
                    "features": [{"attributes": {"ID": 456}}],
                    "count": 1,
                }
            if name == "buffer_and_query":
                return {
                    "buffer_geometry": {"rings": [[]]},
                    "radius": 1000,
                    "unit": "meters",
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "where",
                    "layer": "SUPPORT",
                    "layer_url": "https://x/0",
                    "where": "ID=123",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "buffer",
                            "distance": 1000,
                            "unit": "meters",
                            "children": [
                                {
                                    "type": "where",
                                    "layer": "BUILDINGS",
                                    "layer_url": "https://x/1",
                                }
                            ],
                        }
                    ],
                }
            ],
            "message": "Finding BUILDINGSs near support",
        }
        result = await handler._execute_analyze(plan, time.perf_counter())
        assert result["data"]["source"]["type"] == "feature_query"
        # _buffer_zone + child = 2 results
        assert len(result["data"]["results"]) == 2
        assert result["data"]["results"][0]["layer"] == "_buffer_zone"

    @pytest.mark.asyncio
    async def test_geocode_failure(self):
        """Geocode failure returns error message."""
        handler = _make_handler(call_tool_return={
            "candidates": [], "count": 0
        })
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "nonexistent place",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "buffer",
                            "distance": 1000,
                            "unit": "meters",
                            "children": [
                                {"layer": "X", "layer_url": "https://x/0"}
                            ],
                        }
                    ],
                }
            ],
            "message": "Test",
        }
        result = await handler._execute_analyze(plan, time.perf_counter())
        assert result["action"] == "analyze"
        assert "no candidates" in result["message"]
        assert result["data"] is None

    @pytest.mark.asyncio
    async def test_unrecognized_join_type(self):
        """Unrecognized join_type skips the tool node."""
        handler = _make_handler(call_tool_return={
            "candidates": [
                {"location": {"x": -75, "y": 40}, "score": 95}
            ],
        })
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "20 Church Rd",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "magic_join",
                            "distance": 100,
                            "unit": "meters",
                            "children": [
                                {"layer": "X", "layer_url": "https://x/0"}
                            ],
                        }
                    ],
                }
            ],
            "message": "Test",
        }
        result = await handler._execute_analyze(plan, time.perf_counter())
        assert result["action"] == "analyze"
        assert result["data"]["results"] == []

    @pytest.mark.asyncio
    async def test_multiple_children_shared_buffer(self):
        """Multiple leaf children under one buffer tool node."""
        async def _side_effect(name, args, **kwargs):
            if name == "geocode":
                return {
                    "candidates": [
                        {"location": {"x": -75, "y": 40}, "score": 95}
                    ],
                }
            if name == "buffer_and_query":
                return {
                    "buffer_geometry": {"rings": [[]]},
                    "radius": 3000,
                    "unit": "meters",
                }
            if name == "query_features":
                return {
                    "features": [{"attributes": {"ID": 1}}],
                    "count": 1,
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "address",
                    "address": "100 Main St",
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "buffer",
                            "distance": 3000,
                            "unit": "meters",
                            "children": [
                                {"layer": "TAB", "layer_url": "https://x/0"},
                                {"layer": "SUPPORT", "layer_url": "https://x/1"},
                            ],
                        }
                    ],
                }
            ],
            "message": "Finding tabs and supports",
        }
        result = await handler._execute_analyze(plan, time.perf_counter())
        # _buffer_zone + 2 child layers = 3 results
        assert len(result["data"]["results"]) == 3
        assert result["data"]["results"][0]["layer"] == "_buffer_zone"
        child_layers = {r["layer"] for r in result["data"]["results"][1:]}
        assert child_layers == {"TAB", "SUPPORT"}

    @pytest.mark.asyncio
    async def test_empty_analyze_nodes(self):
        handler = _make_handler()
        plan = {"action": "analyze", "analyze": [], "message": ""}
        result = await handler._execute_analyze(plan, time.perf_counter())
        assert result["action"] == "analyze"
        assert "No analyze nodes" in result["message"]

    @pytest.mark.asyncio
    async def test_coordinates_root(self):
        """Coordinates root — no geocode call."""
        async def _side_effect(name, args, **kwargs):
            if name == "find_nearby":
                return {
                    "features": [
                        {"attributes": {"ID": 1}, "distance": 0.3}
                    ],
                    "count": 1,
                    "total_in_radius": 1,
                    "search_radius": 2.0,
                    "search_unit": "miles",
                }
            return {}

        handler = _make_handler(call_tool_side_effect=_side_effect)
        plan = {
            "action": "analyze",
            "analyze": [
                {
                    "type": "location",
                    "lon": -74.98,
                    "lat": 39.93,
                    "children": [
                        {
                            "type": "tool",
                            "join_type": "proximity",
                            "distance": 2.0,
                            "unit": "miles",
                            "top": 5,
                            "children": [
                                {
                                    "layer": "CUST",
                                    "layer_url": "https://x/0",
                                }
                            ],
                        }
                    ],
                }
            ],
            "message": "Finding nearby",
        }
        result = await handler._execute_analyze(plan, time.perf_counter())
        assert result["data"]["source"]["type"] == "coordinates"
        assert len(result["data"]["results"]) == 1


# ── _validate_plan extended ────────────────────────


class TestValidatePlanExtended:
    """Tests for extended _validate_plan()."""

    def _rag_layers(self):
        return [
            {
                "layer_name": "BUILDINGS",
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
                                    "layer": "BUILDINGS",
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
                                    "layer": "BUILDINGS",
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
                    "layer": "BUILDINGS",
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
                                    "layer": "BUILDINGS",
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
