"""
Unit tests for buffer tool (buffer_and_query).
"""

import json

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.fixture
def mock_ctx():
    ctx = AsyncMock()
    return ctx


SAMPLE_POINT = {"x": -104.9, "y": 39.7, "spatialReference": {"wkid": 4326}}
SAMPLE_GEOJSON_POINT = {"type": "Point", "coordinates": [-104.9, 39.7]}
SAMPLE_BUFFER_POLYGON = {
    "rings": [[[-105, 39], [-105, 40], [-104, 40], [-104, 39], [-105, 39]]],
    "spatialReference": {"wkid": 4326},
}


class TestBufferAndQuery:
    """Tests for buffer_and_query standalone function."""

    @pytest.mark.asyncio
    async def test_buffer_only(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.buffer import buffer_and_query

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER_POLYGON
        result = await buffer_and_query(
            mock_client, mock_ctx, json.dumps(SAMPLE_POINT), radius=500, unit="feet"
        )
        assert "buffer_geometry" in result
        assert result["radius"] == 500
        assert result["unit"] == "feet"
        assert "features" not in result  # no layer_url → no query

    @pytest.mark.asyncio
    async def test_buffer_with_query(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.buffer import buffer_and_query

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER_POLYGON
        mock_client.query_layer.return_value = {
            "features": [
                {"attributes": {"Name": "Parcel A"}, "geometry": SAMPLE_POINT},
            ]
        }
        result = await buffer_and_query(
            mock_client,
            mock_ctx,
            json.dumps(SAMPLE_POINT),
            radius=1000,
            unit="feet",
            layer_url="https://example.com/0",
        )
        assert result["count"] == 1
        assert result["layer_url"] == "https://example.com/0"
        assert len(result["features"]) == 1

    @pytest.mark.asyncio
    async def test_geojson_input(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.buffer import buffer_and_query

        mock_client.buffer_geometry.return_value = SAMPLE_BUFFER_POLYGON
        result = await buffer_and_query(
            mock_client, mock_ctx, json.dumps(SAMPLE_GEOJSON_POINT), radius=100, unit="meters"
        )
        assert "buffer_geometry" in result
        # Verify the geometry was normalized before passing to client
        call_geom = mock_client.buffer_geometry.call_args.kwargs["geometry"]
        assert "x" in call_geom  # normalized to ArcGIS JSON

    @pytest.mark.asyncio
    async def test_invalid_unit(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.buffer import buffer_and_query

        result = await buffer_and_query(
            mock_client, mock_ctx, json.dumps(SAMPLE_POINT), radius=500, unit="furlongs"
        )
        assert result["error"] == "Invalid unit"

    @pytest.mark.asyncio
    async def test_negative_radius(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.buffer import buffer_and_query

        result = await buffer_and_query(
            mock_client, mock_ctx, json.dumps(SAMPLE_POINT), radius=-10, unit="feet"
        )
        assert result["error"] == "Invalid radius"

    @pytest.mark.asyncio
    async def test_zero_radius(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.buffer import buffer_and_query

        result = await buffer_and_query(
            mock_client, mock_ctx, json.dumps(SAMPLE_POINT), radius=0, unit="feet"
        )
        assert result["error"] == "Invalid radius"

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_client, mock_ctx):
        from mcp_arcgis_server.tools.buffer import buffer_and_query

        mock_client.buffer_geometry.side_effect = Exception("server error")
        result = await buffer_and_query(
            mock_client, mock_ctx, json.dumps(SAMPLE_POINT), radius=500, unit="feet"
        )
        assert result["error"] == "buffer_and_query failed"


class TestBufferGeometryFallback:
    """Tests for client.buffer_geometry() fallback behavior.

    Mocks geo_buffer to fail and verifies fallback produces valid geometry.
    """

    @pytest.mark.asyncio
    async def test_fallback_on_geo_buffer_exception(self):
        from unittest.mock import patch, MagicMock

        from mcp_arcgis_server.arcgis.client import ArcGISClient

        mock_auth = MagicMock()
        mock_auth.gis = MagicMock()
        client = ArcGISClient.__new__(ArcGISClient)
        client._auth = mock_auth
        client._closed = False
        import concurrent.futures

        client._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        with patch(
            "arcgis.geometry.functions.buffer",
            side_effect=Exception("geometry service unavailable"),
        ):
            result = await client.buffer_geometry(
                geometry=SAMPLE_POINT, radius=1000, unit="meters"
            )

        client._executor.shutdown(wait=False)

        assert "rings" in result
        assert result["spatialReference"]["wkid"] == 4326
        ring = result["rings"][0]
        assert len(ring) == 65  # 64 + closing vertex
        assert ring[0] == ring[-1]

    @pytest.mark.asyncio
    async def test_fallback_on_empty_geo_buffer_result(self):
        from unittest.mock import patch, MagicMock

        from mcp_arcgis_server.arcgis.client import ArcGISClient

        mock_auth = MagicMock()
        mock_auth.gis = MagicMock()
        client = ArcGISClient.__new__(ArcGISClient)
        client._auth = mock_auth
        client._closed = False
        import concurrent.futures

        client._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        with patch(
            "arcgis.geometry.functions.buffer",
            return_value=[],
        ):
            result = await client.buffer_geometry(
                geometry=SAMPLE_POINT, radius=500, unit="feet"
            )

        client._executor.shutdown(wait=False)

        assert "rings" in result
        assert result["spatialReference"]["wkid"] == 4326

    @pytest.mark.asyncio
    async def test_unit_conversion_in_fallback(self):
        from unittest.mock import patch, MagicMock

        from mcp_arcgis_server.arcgis.client import ArcGISClient
        from mcp_arcgis_server.arcgis.geometry import compute_distance

        mock_auth = MagicMock()
        mock_auth.gis = MagicMock()
        client = ArcGISClient.__new__(ArcGISClient)
        client._auth = mock_auth
        client._closed = False
        import concurrent.futures

        client._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        with patch(
            "arcgis.geometry.functions.buffer",
            side_effect=Exception("fail"),
        ):
            result = await client.buffer_geometry(
                geometry=SAMPLE_POINT, radius=2, unit="kilometers"
            )

        client._executor.shutdown(wait=False)

        ring = result["rings"][0]
        # Check radius is ~2 km
        vertex_pt = {"x": ring[0][0], "y": ring[0][1], "spatialReference": {"wkid": 4326}}
        d = compute_distance(SAMPLE_POINT, vertex_pt, unit="kilometers")
        assert abs(d - 2.0) / 2.0 < 0.05  # within 5%
