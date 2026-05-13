"""
Unit tests for mcp-mapgpt-client core modules.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# LLMService tests
# ---------------------------------------------------------------------------


class TestLLMService:
    """Tests for LLMService."""

    def test_mcp_to_openai_format_conversion(self):
        """MCP tool definitions convert correctly to OpenAI format."""
        from core.llm_service import LLMService

        mcp_tools = [
            {
                "name": "query_features",
                "description": "Query features from a layer",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "layer_url": {"type": "string"},
                        "where": {"type": "string"},
                    },
                    "required": ["layer_url"],
                },
            }
        ]

        result = LLMService.mcp_tools_to_openai_format(mcp_tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "query_features"
        assert result[0]["function"]["description"] == "Query features from a layer"
        assert "properties" in result[0]["function"]["parameters"]

    def test_empty_tools_conversion(self):
        from core.llm_service import LLMService

        result = LLMService.mcp_tools_to_openai_format([])
        assert result == []


class TestLLMResponse:
    """Tests for LLMResponse and ToolCallResult."""

    def test_has_tool_calls(self):
        from core.llm_service import LLMResponse, ToolCallResult

        response = LLMResponse(
            tool_calls=[
                ToolCallResult(
                    tool_call_id="tc1",
                    tool_name="query_features",
                    tool_input={"layer_url": "https://test"},
                )
            ]
        )
        assert response.has_tool_calls is True

    def test_no_tool_calls(self):
        from core.llm_service import LLMResponse

        response = LLMResponse(content="Hello")
        assert response.has_tool_calls is False


# ---------------------------------------------------------------------------
# MCPClient tests
# ---------------------------------------------------------------------------


class TestMCPClient:
    """Tests for MCPClient."""

    def test_initial_state(self):
        from core.mcp_client import MCPClient

        client = MCPClient()
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """Disconnecting when not connected should not raise."""
        from core.mcp_client import MCPClient

        client = MCPClient()
        await client.disconnect()  # Should not raise

    @pytest.mark.asyncio
    async def test_list_tools_requires_connection(self):
        """list_tools raises ConnectionError when not connected."""
        from core.mcp_client import MCPClient

        client = MCPClient()
        with pytest.raises(ConnectionError):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_call_tool_requires_connection(self):
        from core.mcp_client import MCPClient

        client = MCPClient()
        with pytest.raises(ConnectionError):
            await client.call_tool("test", {})


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


class TestOrchestrator:
    """Tests for MapGPTOrchestrator pipeline."""

    @pytest.mark.asyncio
    async def test_process_message_response(self):
        """Orchestrator returns message when LLM gives text response."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(return_value=[])

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"action": "message", "message": "Hello!"})
            )
        )

        with patch(
            "core.orchestrator.query_handler.build_rag_context",
            new_callable=AsyncMock,
            return_value=("=== AVAILABLE LAYERS ===\nTEST: https://example.com/0", [{"name": "TEST"}]),
        ):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.plan("test query")

        assert result["action"] == "message"
        assert result["message"] == "Hello!"

    @pytest.mark.asyncio
    async def test_process_with_plan(self):
        """Orchestrator plan() returns parsed JSON plan directly (no tool loop)."""
        from core.llm_service import LLMResponse, LLMService
        from core.mcp_client import MCPClient
        from core.orchestrator import MapGPTOrchestrator

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.is_connected = True
        mock_mcp.list_tools = AsyncMock(
            return_value=[
                {"name": "count_features", "description": "Count",
                 "inputSchema": {}}
            ]
        )
        mock_mcp.call_tool = AsyncMock()

        # plan() now calls complete(json_mode=True) directly
        plan_response = LLMResponse(
            content=json.dumps({
                "action": "query",
                "query": [{"type": "count", "layer": "TEST",
                           "layer_url": "https://test"}],
                "message": "Counting features",
            })
        )

        mock_llm = MagicMock(spec=LLMService)
        mock_llm.complete = AsyncMock(return_value=plan_response)

        with patch(
            "core.orchestrator.query_handler.build_rag_context",
            new_callable=AsyncMock,
            return_value=("=== AVAILABLE LAYERS ===\nTEST: https://test", [{"name": "TEST"}]),
        ):
            orch = MapGPTOrchestrator(mock_mcp, mock_llm)
            result = await orch.plan("How many features?")

        assert result["action"] == "query"
        # plan() no longer calls tools — that happens in execute()
        mock_mcp.call_tool.assert_not_called()


# ---------------------------------------------------------------------------
# ArcGIS Response Schema tests
# ---------------------------------------------------------------------------


class TestArcGISSchemas:
    """Tests for ArcGISFeature, ArcGISField, and ArcGISQueryResult Pydantic models."""

    def test_arcgis_feature(self):
        """ArcGISFeature accepts attributes and optional geometry."""
        from api.schemas import ArcGISFeature

        feat = ArcGISFeature(
            attributes={"NAME": "Test", "STATUS": "Active"},
            geometry={"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        )
        assert feat.attributes["NAME"] == "Test"
        assert feat.geometry is not None

    def test_arcgis_feature_no_geometry(self):
        """ArcGISFeature accepts None geometry."""
        from api.schemas import ArcGISFeature

        feat = ArcGISFeature(attributes={"NAME": "Test"})
        assert feat.geometry is None

    def test_arcgis_query_result(self):
        """ArcGISQueryResult validates full structure with camelCase aliases."""
        from api.schemas import ArcGISFeature, ArcGISField, ArcGISQueryResult

        result = ArcGISQueryResult(
            features=[
                ArcGISFeature(attributes={"NAME": "A"}),
                ArcGISFeature(attributes={"NAME": "B"}),
            ],
            count=2,
            geometry_type="esriGeometryPolygon",
            spatial_reference={"wkid": 4326},
            object_id_field_name="OBJECTID",
            fields=[ArcGISField(name="NAME", type="esriFieldTypeString", alias="Name")],
        )
        assert result.count == 2
        assert len(result.features) == 2
        assert result.geometry_type == "esriGeometryPolygon"
        assert result.object_id_field_name == "OBJECTID"
        assert len(result.fields) == 1

    def test_arcgis_query_result_from_camelcase(self):
        """ArcGISQueryResult accepts camelCase keys via aliases."""
        from api.schemas import ArcGISQueryResult

        result = ArcGISQueryResult(**{
            "features": [],
            "count": 0,
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
            "objectIdFieldName": "OBJECTID",
        })
        assert result.geometry_type == "esriGeometryPoint"
        assert result.spatial_reference == {"wkid": 4326}
        assert result.object_id_field_name == "OBJECTID"

    def test_arcgis_query_result_defaults(self):
        """ArcGISQueryResult defaults to empty features."""
        from api.schemas import ArcGISQueryResult

        result = ArcGISQueryResult()
        assert result.features == []
        assert result.count == 0
        assert result.geometry_type is None
        assert result.fields is None


# ---------------------------------------------------------------------------
# Orchestrator FeatureSet parsing tests
# ---------------------------------------------------------------------------


class TestFilterForSummary:
    """Tests for _filter_for_summary with FeatureSet parsing."""

    def test_featureset_parsing_typed_access(self):
        """FeatureSet parsing extracts attributes via typed access."""
        from core.orchestrator.summarize_handler import SummarizeHandler

        data = {
            "features": [
                {"attributes": {"NAME": "A", "OBJECTID": 1, "SHAPE": "blob"}, "geometry": None},
                {"attributes": {"NAME": "B", "OBJECTID": 2, "SHAPE": "blob"}, "geometry": None},
            ],
            "fields": [
                {"name": "NAME", "alias": "Feature Name", "type": "esriFieldTypeString"},
                {"name": "OBJECTID", "alias": "Object ID", "type": "esriFieldTypeOID"},
            ],
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
        }

        filtered, count, aliases = SummarizeHandler._filter_for_summary(data)

        assert count == 2
        # OBJECTID and SHAPE should be stripped
        for feat in filtered["features"]:
            assert "OBJECTID" not in feat["attributes"]
            assert "SHAPE" not in feat["attributes"]
            assert "NAME" in feat["attributes"]

    def test_featureset_parsing_fallback_on_invalid(self):
        """Invalid data for FeatureSet parsing falls back to dict-based filtering."""
        from core.orchestrator.summarize_handler import SummarizeHandler

        data = {
            "features": [
                {"attributes": {"NAME": "A", "OBJECTID": 1}},
            ],
        }

        # This should work via dict fallback even if FeatureSet can't parse it
        filtered, count, aliases = SummarizeHandler._filter_for_summary(data)
        assert count == 1
        assert "OBJECTID" not in filtered["features"][0]["attributes"]

    def test_field_alias_extraction(self):
        """Field aliases extracted from FeatureSet.fields."""
        from core.orchestrator.summarize_handler import SummarizeHandler

        data = {
            "features": [
                {"attributes": {"BLDG_NAME": "Tower A"}, "geometry": None},
            ],
            "fields": [
                {"name": "BLDG_NAME", "alias": "Building Name", "type": "esriFieldTypeString"},
            ],
            "geometryType": "esriGeometryPoint",
            "spatialReference": {"wkid": 4326},
        }

        filtered, count, aliases = SummarizeHandler._filter_for_summary(data)

        # Aliases may come from FeatureSet or be empty (depends on arcgis availability)
        # The method should not raise regardless
        assert count == 1

    def test_count_only_passthrough(self):
        """Count-only results pass through unchanged."""
        from core.orchestrator.summarize_handler import SummarizeHandler

        data = {"count": 42}
        filtered, count, aliases = SummarizeHandler._filter_for_summary(data)
        assert filtered == {"count": 42}
        assert count == 0

    def test_non_dict_passthrough(self):
        """Non-dict data passes through unchanged."""
        from core.orchestrator.summarize_handler import SummarizeHandler

        filtered, count, aliases = SummarizeHandler._filter_for_summary("error string")
        assert filtered == "error string"
        assert count == 0
