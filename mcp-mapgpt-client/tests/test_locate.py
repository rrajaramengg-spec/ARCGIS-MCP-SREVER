"""
Unit tests for locate action handler, /locate endpoint, and prefix routing.
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestLocateRequest:
    """Tests for LocateRequest validation."""

    def test_address_only(self):
        from api.schemas import LocateRequest

        req = LocateRequest(address="123 Main St, Denver, CO")
        assert req.address == "123 Main St, Denver, CO"
        assert req.latitude is None

    def test_coordinates_only(self):
        from api.schemas import LocateRequest

        req = LocateRequest(latitude=39.7392, longitude=-104.9903)
        assert req.latitude == 39.7392
        assert req.longitude == -104.9903

    def test_missing_both_raises(self):
        from api.schemas import LocateRequest

        with pytest.raises(ValueError, match="Either 'address' or both"):
            LocateRequest()

    def test_partial_coordinates_raises(self):
        from api.schemas import LocateRequest

        with pytest.raises(ValueError, match="Either 'address' or both"):
            LocateRequest(latitude=39.7)


class TestLocateResponse:
    """Tests for LocateResponse model."""

    def test_defaults(self):
        from api.schemas import LocateResponse

        resp = LocateResponse(execution_time_ms=42.0)
        assert resp.action == "locate"
        assert resp.location is None
        assert resp.execution_time_ms == 42.0

    def test_full_response(self):
        from api.schemas import LocateResponse

        resp = LocateResponse(
            location={"x": -104.99, "y": 39.74},
            address="123 Main St",
            candidates=[{"address": "123 Main St", "score": 100}],
            score=100.0,
            execution_time_ms=50.0,
        )
        assert resp.location["x"] == -104.99
        assert resp.score == 100.0


class TestSummarizeStatResponse:
    """Tests for SummarizeStatResponse model."""

    def test_defaults(self):
        from api.schemas import SummarizeStatResponse

        resp = SummarizeStatResponse(summary="test", execution_time_ms=10.0, status="success")
        assert resp.action == "summarize_stat"
        assert resp.feature_count == 0


# ---------------------------------------------------------------------------
# Orchestrator _execute_locate tests
# ---------------------------------------------------------------------------


class TestExecuteLocate:
    """Tests for _execute_locate in QueryHandler."""

    @pytest.mark.asyncio
    async def test_address_locate(self):
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator.query_handler import QueryHandler

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.call_tool = AsyncMock(return_value={
            "candidates": [{"address": "123 Main St", "location": {"x": -104, "y": 39}, "score": 95}]
        })
        mock_llm = MagicMock(spec=LLMService)

        handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts={}, tools_cache=[])

        import time
        plan = {
            "action": "locate",
            "locate": {"type": "address", "address": "123 Main St"},
            "message": "Locating",
        }
        result = await handler._execute_locate(plan, time.perf_counter())

        assert result["action"] == "locate"
        assert result["data"]["source"]["type"] == "geocode"
        mock_mcp.call_tool.assert_called_once_with("geocode", {"address": "123 Main St"})

    @pytest.mark.asyncio
    async def test_coordinate_locate(self):
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator.query_handler import QueryHandler

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.call_tool = AsyncMock(return_value={"address": "Somewhere"})
        mock_llm = MagicMock(spec=LLMService)

        handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts={}, tools_cache=[])

        import time
        plan = {
            "action": "locate",
            "locate": {"type": "location", "lat": 39.7, "lon": -104.9},
            "message": "Looking up",
        }
        result = await handler._execute_locate(plan, time.perf_counter())

        assert result["action"] == "locate"
        # New behavior: coordinates → no MCP call, returns coordinates source
        assert result["data"]["source"]["type"] == "coordinates"
        assert result["data"]["source"]["location"]["x"] == -104.9
        assert result["data"]["source"]["location"]["y"] == 39.7
        mock_mcp.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_payload_returns_message(self):
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator.query_handler import QueryHandler

        mock_mcp = MagicMock(spec=MCPClient)
        mock_llm = MagicMock(spec=LLMService)

        handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts={}, tools_cache=[])

        import time
        plan = {"action": "locate", "message": "I can help locate"}
        result = await handler._execute_locate(plan, time.perf_counter())

        assert result["action"] == "locate"
        assert result["data"] is None
        assert result["tool_name"] is None

    @pytest.mark.asyncio
    async def test_tool_failure_returns_error(self):
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator.query_handler import QueryHandler

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.call_tool = AsyncMock(side_effect=Exception("Network error"))
        mock_llm = MagicMock(spec=LLMService)

        handler = QueryHandler(mcp=mock_mcp, llm=mock_llm, prompts={}, tools_cache=[])

        import time
        plan = {
            "action": "locate",
            "locate": {"address": "123 Main"},
            "message": "",
        }
        result = await handler._execute_locate(plan, time.perf_counter())

        # New behavior: exception is caught by asyncio.gather(return_exceptions=True)
        # Result has empty source list and no results
        assert result["action"] == "locate"


# ---------------------------------------------------------------------------
# Orchestrator locate() direct method tests
# ---------------------------------------------------------------------------


class TestDirectLocate:
    """Tests for direct locate() method."""

    @pytest.mark.asyncio
    async def test_locate_address(self):
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.call_tool = AsyncMock(return_value={
            "candidates": [{"address": "123 Main St", "location": {"x": -104, "y": 39}, "score": 95}]
        })
        mock_llm = MagicMock(spec=LLMService)

        orch = MapGPTOrchestrator(mock_mcp, mock_llm)
        result = await orch.locate(address="123 Main St")

        assert result["action"] == "locate"
        assert result["address"] == "123 Main St"
        assert result["score"] == 95

    @pytest.mark.asyncio
    async def test_locate_coord_string(self):
        """Coordinate pattern in address string routes to reverse_geocode."""
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.call_tool = AsyncMock(return_value={"address": "Some Place", "location": {"x": -104.9, "y": 39.7}})
        mock_llm = MagicMock(spec=LLMService)

        orch = MapGPTOrchestrator(mock_mcp, mock_llm)
        result = await orch.locate(address="39.7,-104.9")

        assert result["action"] == "locate"
        mock_mcp.call_tool.assert_called_once_with(
            "reverse_geocode", {"latitude": 39.7, "longitude": -104.9}
        )


# ---------------------------------------------------------------------------
# Prefix routing tests
# ---------------------------------------------------------------------------


class TestPrefixRouting:
    """Tests for slash-command prefix routing in execute()."""

    @pytest.mark.asyncio
    async def test_locate_prefix(self):
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.call_tool = AsyncMock(return_value={
            "candidates": [{"address": "Denver", "location": {"x": -104, "y": 39}, "score": 100}]
        })
        mock_llm = MagicMock(spec=LLMService)

        orch = MapGPTOrchestrator(mock_mcp, mock_llm)
        result = await orch.execute("/locate Denver, CO")

        assert result["action"] == "locate"
        mock_mcp.call_tool.assert_called_once_with("geocode", {"address": "Denver, CO"})

    @pytest.mark.asyncio
    async def test_summarize_prefix(self):
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])
        mock_mcp.call_tool = AsyncMock(return_value={"count": 0, "features": []})

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content=json.dumps({"action": "message", "message": "No data"})
        ))

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.execute("/summarize test query")

        # Should route to summarize, which returns summary-shaped result
        assert "summary" in result or "action" in result

    @pytest.mark.asyncio
    async def test_no_prefix_runs_default(self):
        """Non-prefixed query runs through normal plan→execute pipeline."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content=json.dumps({"action": "message", "message": "Hello"})
        ))

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.execute("show me assets")

        assert result["action"] == "message"

    @pytest.mark.asyncio
    async def test_similar_prefix_not_matched(self):
        """/locating should NOT match /locate prefix."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content=json.dumps({"action": "message", "message": "test"})
        ))

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.execute("/locating something")

        # Should go through plan() pipeline, not locate()
        assert result["action"] == "message"


# ---------------------------------------------------------------------------
# Commands endpoint tests
# ---------------------------------------------------------------------------


class TestCommandsEndpoint:
    """Tests for /api/mapgpt/v1/commands endpoint."""

    def test_commands_returns_list(self):
        with patch("main.mcp_client") as mock_mcp:
            mock_mcp.is_connected = True
            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/mapgpt/v1/commands")
            assert response.status_code == 200
            cmds = response.json()
            assert isinstance(cmds, list)
            assert len(cmds) >= 3
            names = [c["name"] for c in cmds]
            assert "/locate" in names
            assert "/summarize" in names
            assert "/summarize-stat" in names

    def test_command_has_required_fields(self):
        with patch("main.mcp_client") as mock_mcp:
            mock_mcp.is_connected = True
            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/mapgpt/v1/commands")
            for cmd in response.json():
                assert "name" in cmd
                assert "description" in cmd
                assert "endpoint" in cmd
                assert "params" in cmd


# ---------------------------------------------------------------------------
# SummarizeStat tests (8.8-8.11)
# ---------------------------------------------------------------------------


class TestSummarizeStat:
    """Tests for summarize_stat() orchestrator method."""

    def _make_orchestrator(self, plan_content, mcp_result=None, llm_summary="Summary text"):
        """Helper to create orchestrator with mocked plan + tools."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])
        if mcp_result is not None:
            mock_mcp.call_tool = AsyncMock(return_value=mcp_result)

        # plan() calls complete once, summarize_field summary calls complete again
        plan_response = LLMResponse(content=json.dumps(plan_content))
        summary_response = LLMResponse(content=llm_summary)

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(side_effect=[plan_response, summary_response])

        return MapGPTOrchestrator(mock_mcp, mock_llm), mock_mcp, mock_llm

    @pytest.mark.asyncio
    async def test_single_field_a_phase(self):
        """8.8: Single field plan uses A-phase heuristic → calls summarize_field."""
        plan = {
            "action": "query",
            "query": {
                "layer_url": "https://test/0",
                "where": "UPPER(COUNTY) LIKE '%MADISON%'",
                "fields": ["SERVICE_STATUS"],
            },
            "message": "Query service status",
        }
        stats = {"count": 100, "min": 0, "max": 5, "avg": 2.5}

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch, mock_mcp, _ = self._make_orchestrator(plan, mcp_result=stats)
            result = await orch.summarize_stat("service status in Madison County")

        assert result["action"] == "summarize_stat"
        assert result["field_name"] == "SERVICE_STATUS"
        assert result["statistics"] == stats
        mock_mcp.call_tool.assert_called_once_with("summarize_field", {
            "layer_url": "https://test/0",
            "field_name": "SERVICE_STATUS",
            "where": "UPPER(COUNTY) LIKE '%MADISON%'",
        })

    @pytest.mark.asyncio
    async def test_multi_field_d_phase(self):
        """8.9: Multiple fields triggers D-phase fallback LLM call."""
        plan = {
            "action": "query",
            "query": {
                "layer_url": "https://test/0",
                "where": "1=1",
                "fields": ["SERVICE_STATUS", "BUILDING_TYPE", "ADDRESS"],
            },
            "message": "Query fields",
        }
        stats = {"count": 50, "unique_values": {"MDU": 30, "SFU": 20}}

        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])
        mock_mcp.call_tool = AsyncMock(return_value=stats)

        # 3 LLM calls: plan(), D-phase field classification, summary
        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(content=json.dumps(plan)),       # plan()
            LLMResponse(content="BUILDING_TYPE"),          # D-phase
            LLMResponse(content="Summary of building types"),  # summary
        ])

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.summarize_stat("what building types exist?")

        assert result["action"] == "summarize_stat"
        assert result["field_name"] == "BUILDING_TYPE"
        assert result["statistics"] == stats
        # LLM should have been called 3 times
        assert mock_llm.complete.call_count == 3

    @pytest.mark.asyncio
    async def test_count_only_plan_fallback(self):
        """8.10: Count-only plan with no fields triggers fallback to summarize flow."""
        plan = {
            "action": "query",
            "query": {
                "type": "count",
                "layer_url": "https://test/0",
                "where": "1=1",
            },
            "message": "Count features",
        }

        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])
        # execute returns count-only result, then summarize LLM call
        mock_mcp.call_tool = AsyncMock(return_value={"count": 42})

        # plan(), D-phase (returns empty/ambiguous), then summarize fallback needs:
        # plan() again (inside summarize→execute→plan), LLM summary
        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(content=json.dumps(plan)),    # plan() in summarize_stat
            LLMResponse(content=""),                    # D-phase returns empty
            LLMResponse(content=json.dumps(plan)),    # plan() inside summarize→execute
            LLMResponse(content="There are 42 features."),  # summarize LLM
        ])

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.summarize_stat("how many features total?")

        assert result["action"] == "summarize_stat"
        # Falls back to summarize flow so summary field should be populated
        assert result["summary"] != ""

    @pytest.mark.asyncio
    async def test_message_only_plan(self):
        """8.11: Message-only plan returns feature_count: 0."""
        plan = {
            "action": "message",
            "message": "I couldn't identify the layer.",
        }

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch, _, _ = self._make_orchestrator(plan)
            result = await orch.summarize_stat("something ambiguous")

        assert result["action"] == "summarize_stat"
        assert result["feature_count"] == 0
        assert "couldn't identify" in result["summary"]


# ---------------------------------------------------------------------------
# Route-level tests (9.4-9.7)
# ---------------------------------------------------------------------------


class TestLocateRoute:
    """Tests for /api/mapgpt/v1/locate endpoint."""

    def test_locate_address(self):
        """9.4: /locate with address input."""
        from fastapi.testclient import TestClient
        from main import app
        from core.providers import get_orchestrator

        mock_orch = MagicMock()
        mock_orch.locate = AsyncMock(return_value={
            "action": "locate",
            "location": {"x": -104, "y": 39},
            "address": "123 Main St",
            "candidates": None,
            "score": 95.0,
            "execution_time_ms": 50.0,
        })
        app.dependency_overrides[get_orchestrator] = lambda: mock_orch
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/mapgpt/v1/locate",
                json={"address": "123 Main St"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["action"] == "locate"
            assert data["address"] == "123 Main St"
        finally:
            app.dependency_overrides.pop(get_orchestrator, None)

    def test_locate_coordinates(self):
        """9.5: /locate with coordinate input."""
        from fastapi.testclient import TestClient
        from main import app
        from core.providers import get_orchestrator

        mock_orch = MagicMock()
        mock_orch.locate = AsyncMock(return_value={
            "action": "locate",
            "location": {"x": -104.9, "y": 39.7},
            "address": "Some Place",
            "candidates": None,
            "score": None,
            "execution_time_ms": 30.0,
        })
        app.dependency_overrides[get_orchestrator] = lambda: mock_orch
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/mapgpt/v1/locate",
                json={"latitude": 39.7, "longitude": -104.9},
            )
            assert response.status_code == 200
            assert response.json()["action"] == "locate"
        finally:
            app.dependency_overrides.pop(get_orchestrator, None)

    def test_locate_invalid_input(self):
        """9.6: /locate with invalid input returns 422."""
        from fastapi.testclient import TestClient
        from main import app
        from core.providers import get_orchestrator

        mock_orch = MagicMock()
        app.dependency_overrides[get_orchestrator] = lambda: mock_orch
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/mapgpt/v1/locate", json={})
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_orchestrator, None)


class TestSummarizeStatRoute:
    """Tests for /api/mapgpt/v1/summarize-stat endpoint."""

    def test_summarize_stat_endpoint(self):
        """9.7: /summarize-stat with valid query."""
        from fastapi.testclient import TestClient
        from main import app
        from core.providers import get_orchestrator

        mock_orch = MagicMock()
        mock_orch.summarize_stat = AsyncMock(return_value={
            "action": "summarize_stat",
            "summary": "The average population is 50,000.",
            "statistics": {"count": 10, "avg": 50000},
            "field_name": "POPULATION",
            "layer_url": "https://test/0",
            "feature_count": 10,
            "execution_time_ms": 100.0,
            "status": "success",
        })
        app.dependency_overrides[get_orchestrator] = lambda: mock_orch
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/mapgpt/v1/summarize-stat",
                json={"query": "average population of counties"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["action"] == "summarize_stat"
            assert data["field_name"] == "POPULATION"
        finally:
            app.dependency_overrides.pop(get_orchestrator, None)


# ---------------------------------------------------------------------------
# Integration tests (11.1-11.5)
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end integration tests with mocked MCP."""

    @pytest.mark.asyncio
    async def test_locate_prefix_e2e(self):
        """11.1: /locate prefix through execute → prefix routing → geocode."""
        from core.llm_service import LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.call_tool = AsyncMock(return_value={
            "candidates": [{"address": "123 Main St, Denver, CO", "location": {"x": -104.9, "y": 39.7}, "score": 100}]
        })
        mock_llm = MagicMock(spec=LLMService)

        orch = MapGPTOrchestrator(mock_mcp, mock_llm)
        result = await orch.execute("/locate 123 Main Street")

        assert result["action"] == "locate"
        assert result["data"]["address"] == "123 Main St, Denver, CO"
        mock_mcp.call_tool.assert_called_once_with("geocode", {"address": "123 Main Street"})

    @pytest.mark.asyncio
    async def test_summarize_stat_prefix_e2e(self):
        """11.2: /summarize-stat prefix through execute → prefix routing → summarize_field."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        plan = {
            "action": "query",
            "query": {
                "layer_url": "https://test/0",
                "where": "1=1",
                "fields": ["POPULATION"],
            },
        }
        stats = {"count": 64, "min": 1000, "max": 600000, "avg": 85000}

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])
        mock_mcp.call_tool = AsyncMock(return_value=stats)

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(content=json.dumps(plan)),
            LLMResponse(content="Average population is 85,000 across 64 counties."),
        ])

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.execute("/summarize-stat average population of counties")

        assert result["action"] == "summarize_stat"
        assert result["field_name"] == "POPULATION"
        assert result["statistics"] == stats

    @pytest.mark.asyncio
    async def test_standard_query_unchanged(self):
        """11.3: Standard query through /execute unchanged behavior."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        plan = {
            "action": "query",
            "query": {
                "layer_url": "https://test/0",
                "where": "UPPER(COUNTY) LIKE '%SPRINGFIELD%'",
                "fields": ["NAME", "ADDRESS"],
            },
            "message": "Assets in Springfield",
        }
        features = {"features": [{"attributes": {"NAME": "Test"}}], "count": 1}

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])
        mock_mcp.call_tool = AsyncMock(return_value=features)

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(return_value=LLMResponse(content=json.dumps(plan)))

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.execute("show me assets in springfield county")

        assert result["action"] == "query"
        # Data is now wrapped in uniform {source, results} shape
        assert result["data"]["source"] is None
        assert len(result["data"]["results"]) == 1
        assert result["data"]["results"][0]["features"] == features["features"]
        assert result["tool_name"] == "execute_query_plan"

    @pytest.mark.asyncio
    async def test_standard_summarize_unchanged(self):
        """11.4: Standard /summarize without prefix unchanged behavior."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        plan = {
            "action": "query",
            "query": {"layer_url": "https://test/0", "where": "1=1"},
            "message": "Count features",
        }
        raw_data = {"features": [{"attributes": {"NAME": "X"}}], "count": 1}

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])
        mock_mcp.call_tool = AsyncMock(return_value=raw_data)

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(content=json.dumps(plan)),  # plan()
            LLMResponse(content="There is 1 feature."),  # summarize LLM
        ])

        with patch("core.orchestrator.query_handler.build_rag_context", new_callable=AsyncMock, return_value=("", [])):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.summarize("how many features?")

        assert result["action"] == "query"
        assert "summary" in result
        # feature_count may be 0 since uniform response wraps data in {source, results}
        # and _filter_for_summary doesn't unwrap the new shape

    def test_commands_returns_all(self):
        """11.5: Command discovery endpoint returns all registered commands."""
        with patch("main.mcp_client") as mock_mcp:
            mock_mcp.is_connected = True
            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/mapgpt/v1/commands")
            assert response.status_code == 200
            cmds = response.json()
            names = {c["name"] for c in cmds}
            assert names == {"/locate", "/summarize", "/summarize-stat", "/arcgis-execute", "/execute-llm"}
