"""
Integration tests for in-process MCP transport and HTTP transport.
Tests: create server → connect in-process → list tools → call tools.
Tests: HTTP /health endpoint via ASGI transport.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_in_process_transport_list_tools():
    """Create server → connect in-process → list tools."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, client, auth = create_server()

            async with connect_in_process(mcp) as session:
                result = await session.list_tools()
                tool_names = {t.name for t in result.tools}
                assert "query_features" in tool_names
                assert "count_features" in tool_names
                assert "spatial_join_query" in tool_names
                assert "join_layers" in tool_names
                assert "execute_query_plan" in tool_names
                assert "search_content" in tool_names
                assert "search_layers" in tool_names
                assert "summarize_field" in tool_names
                assert "get_feature_table" in tool_names
                assert "buffer_and_query" in tool_names
                assert "find_nearby" in tool_names
                assert "geocode" in tool_names
                assert "reversegeocode" in tool_names
                assert "union_geometries" in tool_names
                assert len(tool_names) == 14

            client.close()


@pytest.mark.asyncio
async def test_in_process_transport_call_tool():
    """Create server → connect in-process → call query_features with mock."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, arcgis_client, auth = create_server()

            # Mock the query_layer to return test data
            mock_result = {
                "features": [{"attributes": {"NAME": "Test"}}],
                "count": 1,
            }

            async def mock_query_layer(**kwargs):
                return mock_result

            arcgis_client.query_layer = mock_query_layer

            async with connect_in_process(mcp) as session:
                result = await session.call_tool(
                    "query_features",
                    {
                        "layer_url": "https://public.example.com/FeatureServer/0",
                        "where": "1=1",
                    },
                )
                # MCP returns content blocks
                assert result.content
                text = result.content[0].text
                data = json.loads(text)
                assert data["count"] == 1

            arcgis_client.close()


@pytest.mark.asyncio
async def test_multiple_sequential_connections():
    """Multiple sequential in-process connections work without state leakage."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, client, auth = create_server()

            for _ in range(3):
                async with connect_in_process(mcp) as session:
                    result = await session.list_tools()
                    assert len(result.tools) == 14

            client.close()


@pytest.mark.asyncio
async def test_search_content_via_in_process():
    """Call search_content via in-process transport with mocked client."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, arcgis_client, auth = create_server()

            async def mocksearch_content(query, item_type=None, max_items=10):
                return [{"title": "Parcels", "type": "Feature Layer"}]

            arcgis_client.search_content = mocksearch_content

            async with connect_in_process(mcp) as session:
                result = await session.call_tool(
                    "search_content", {"query": "parcels"}
                )
                data = json.loads(result.content[0].text)
                assert data["count"] == 1
                assert data["items"][0]["title"] == "Parcels"

            arcgis_client.close()


@pytest.mark.asyncio
async def test_buffer_and_query_via_in_process():
    """Call buffer_and_query via in-process transport with mocked client."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, arcgis_client, auth = create_server()

            buffer_poly = {
                "rings": [[[-105, 39], [-105, 40], [-104, 40], [-104, 39], [-105, 39]]],
                "spatialReference": {"wkid": 4326},
            }

            async def mock_buffer(geometry, radius, unit="feet", out_sr=4326):
                return buffer_poly

            arcgis_client.buffer_geometry = mock_buffer

            async with connect_in_process(mcp) as session:
                result = await session.call_tool(
                    "buffer_and_query",
                    {
                        "geometry": json.dumps(
                            {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
                        ),
                        "radius": 500,
                        "unit": "feet",
                    },
                )
                data = json.loads(result.content[0].text)
                assert "buffer_geometry" in data
                assert data["radius"] == 500

            arcgis_client.close()


@pytest.mark.asyncio
async def test_summarize_field_via_in_process():
    """Call summarize_field via in-process transport with mocked client."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, arcgis_client, auth = create_server()

            async def mock_get_layer_info(layer_url):
                return {"fields": [{"name": "Pop", "type": "esriFieldTypeInteger"}]}

            async def mock_get_field_stats(layer_url, field_name, statistics, where="1=1"):
                return {"count_Pop": 100, "min_Pop": 1, "max_Pop": 999, "avg_Pop": 50, "stddev_Pop": 10}

            arcgis_client.get_layer_info = mock_get_layer_info
            arcgis_client.get_field_statistics = mock_get_field_stats

            async with connect_in_process(mcp) as session:
                result = await session.call_tool(
                    "summarize_field",
                    {
                        "layer_url": "https://example.com/FeatureServer/0",
                        "field_name": "Pop",
                    },
                )
                data = json.loads(result.content[0].text)
                assert data["field"] == "Pop"
                assert "statistics" in data

            arcgis_client.close()


@pytest.mark.asyncio
async def test_geocode_via_in_process():
    """Call geocode via in-process transport with mocked client."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, arcgis_client, auth = create_server()

            async def mockgeocode(address, max_results=1, out_sr=4326):
                return [
                    {"score": 100, "address": "Denver, CO", "location": {"x": -104.9, "y": 39.7}}
                ]

            arcgis_client.geocode = mockgeocode

            async with connect_in_process(mcp) as session:
                result = await session.call_tool(
                    "geocode", {"address": "Denver, CO"}
                )
                data = json.loads(result.content[0].text)
                assert data["count"] == 1
                assert data["candidates"][0]["address"] == "Denver, CO"

            arcgis_client.close()


@pytest.mark.asyncio
async def test_reverse_geocode_via_in_process():
    """Call reversegeocode via in-process transport with mocked client."""
    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server import create_server, connect_in_process

            mcp, arcgis_client, auth = create_server()

            async def mock_reverse(latitude, longitude, distance=100):
                return {
                    "address": "123 Main St, Denver, CO",
                    "location": {"x": longitude, "y": latitude},
                }

            arcgis_client.reverse_geocode = mock_reverse

            async with connect_in_process(mcp) as session:
                result = await session.call_tool(
                    "reversegeocode",
                    {"latitude": 39.7, "longitude": -104.9},
                )
                data = json.loads(result.content[0].text)
                assert data["address"] == "123 Main St, Denver, CO"

            arcgis_client.close()


# ---------------------------------------------------------------------------
# HTTP transport tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint():
    """HTTP /health endpoint returns status ok via ASGI transport."""
    import httpx

    env = {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            from mcp_arcgis_server.server import create_server
            from mcp_arcgis_server.transport.http import create_app

            mcp, client, auth = create_server()
            app = create_app(mcp)

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert data["service"] == "mcp-arcgis-server"

            client.close()
