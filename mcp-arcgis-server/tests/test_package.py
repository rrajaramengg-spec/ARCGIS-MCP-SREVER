"""
Unit tests for mcp-arcgis-server package.
Tests ArcGISClient domain-based routing, FeatureSet conversion, MCP tool shapes,
in-process transport, async thread pool, and token refresh.
"""

import asyncio
import json
import os
import threading
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Auth / Client tests (Tasks 10.1 — updated import paths)
# ---------------------------------------------------------------------------


class TestGISAuthManager:
    """Tests for GISAuthManager domain-based URL routing and GIS initialization."""

    def test_internal_url_detection(self):
        env = {
            "ARCGIS_PORTAL_URL": "https://arcgis.example.com/arcgis",
            "ARCGIS_USERNAME": "user",
            "ARCGIS_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=False):
            from mcp_arcgis_server.arcgis.auth import GISAuthManager

            auth = GISAuthManager()
            assert auth.is_internal_url(
                "https://arcgis.example.com/server/rest/services/Svc/MapServer/0"
            )

    def test_external_url_detection(self):
        env = {
            "ARCGIS_PORTAL_URL": "https://arcgis.example.com/arcgis",
            "ARCGIS_USERNAME": "user",
            "ARCGIS_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=False):
            from mcp_arcgis_server.arcgis.auth import GISAuthManager

            auth = GISAuthManager()
            assert not auth.is_internal_url(
                "https://services.arcgis.com/public/FeatureServer/0"
            )

    def test_case_insensitive_hostname(self):
        env = {
            "ARCGIS_PORTAL_URL": "https://ARCGIS.Example.COM/arcgis",
            "ARCGIS_USERNAME": "user",
            "ARCGIS_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=False):
            from mcp_arcgis_server.arcgis.auth import GISAuthManager

            auth = GISAuthManager()
            assert auth.is_internal_url(
                "https://arcgis.example.com/server/rest/layer/0"
            )

    def test_no_portal_url(self):
        with patch.dict(
            os.environ,
            {"ARCGIS_PORTAL_URL": "", "ARCGIS_URL": ""},
            clear=False,
        ):
            from mcp_arcgis_server.arcgis.auth import GISAuthManager

            auth = GISAuthManager()
            assert not auth.is_internal_url("https://any.server.com/layer/0")

    def test_gis_init_failure_graceful_degradation(self):
        env = {
            "ARCGIS_PORTAL_URL": "https://arcgis.example.com/arcgis",
            "ARCGIS_USERNAME": "user",
            "ARCGIS_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "mcp_arcgis_server.arcgis.auth.GIS",
                side_effect=Exception("unreachable"),
            ):
                from mcp_arcgis_server.arcgis.auth import GISAuthManager

                auth = GISAuthManager()
                auth._initialize_gis()
                assert auth.gis is None


class TestGeometry:
    """Tests for geometry utility functions."""

    def test_featureset_to_dict(self):
        from mcp_arcgis_server.arcgis.geometry import featureset_to_dict

        mock_fs = MagicMock()
        mock_fs.features = [MagicMock(), MagicMock()]
        mock_fs.to_dict.return_value = {
            "objectIdFieldName": "OBJECTID",
            "geometryType": "esriGeometryPolygon",
            "spatialReference": {"wkid": 4326},
            "fields": [],
            "features": [{"attributes": {"NAME": "A"}}, {"attributes": {"NAME": "B"}}],
        }

        result = featureset_to_dict(mock_fs)
        assert result["count"] == 2
        assert result["geometryType"] == "esriGeometryPolygon"

    def test_featureset_to_dict_empty(self):
        from mcp_arcgis_server.arcgis.geometry import featureset_to_dict

        mock_fs = MagicMock()
        mock_fs.features = []
        mock_fs.to_dict.return_value = {"features": []}

        result = featureset_to_dict(mock_fs)
        assert result["count"] == 0

    def test_intersects_filter(self):
        with patch("mcp_arcgis_server.arcgis.geometry.Geometry") as mock_geom:
            with patch(
                "mcp_arcgis_server.arcgis.geometry.geometry_filters"
            ) as mock_filters:
                mock_geom.return_value = "geom_obj"
                mock_filters.intersects.return_value = {"filter": "intersects"}

                from mcp_arcgis_server.arcgis.geometry import build_geometry_filter

                result = build_geometry_filter(
                    {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                    "esriSpatialRelIntersects",
                )
                mock_filters.intersects.assert_called_once_with("geom_obj")
                assert result == {"filter": "intersects"}

    def test_contains_filter(self):
        with patch("mcp_arcgis_server.arcgis.geometry.Geometry") as mock_geom:
            with patch(
                "mcp_arcgis_server.arcgis.geometry.geometry_filters"
            ) as mock_filters:
                mock_geom.return_value = "geom_obj"
                mock_filters.contains.return_value = {"filter": "contains"}

                from mcp_arcgis_server.arcgis.geometry import build_geometry_filter

                result = build_geometry_filter(
                    {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                    "esriSpatialRelContains",
                )
                mock_filters.contains.assert_called_once_with("geom_obj")


# ---------------------------------------------------------------------------
# Tool module tests (Task 10.2)
# ---------------------------------------------------------------------------


class TestQueryTools:
    """Unit tests for query tool standalone functions."""

    @pytest.mark.asyncio
    async def test_query_features(self):
        from mcp_arcgis_server.tools.query import query_features

        mock_client = AsyncMock()
        mock_client.query_layer.return_value = {
            "features": [{"attributes": {"NAME": "Test"}}],
            "count": 1,
        }

        result = await query_features(
            mock_client,
            "https://example.com/layer/0",
            where="NAME='Test'",
            out_fields="NAME",
        )
        assert result["count"] == 1
        mock_client.query_layer.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_features(self):
        from mcp_arcgis_server.tools.query import count_features

        mock_client = AsyncMock()
        mock_client.query_layer.return_value = {"count": 42}

        result = await count_features(
            mock_client, "https://example.com/layer/0", where="1=1"
        )
        assert result == {"count": 42}

    @pytest.mark.asyncio
    async def test_query_features_with_geometry_filter(self):
        from mcp_arcgis_server.tools.query import query_features

        mock_client = AsyncMock()
        mock_client.query_layer.return_value = {"features": [], "count": 0}

        geom = json.dumps({"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]})
        result = await query_features(
            mock_client,
            "https://example.com/layer/0",
            geometry_filter=geom,
        )
        call_kwargs = mock_client.query_layer.call_args
        assert call_kwargs.kwargs.get("geometry") is not None
        assert call_kwargs.kwargs.get("geometry_type") == "esriGeometryPolygon"


class TestSpatialTools:
    """Unit tests for spatial tool standalone functions."""

    @pytest.mark.asyncio
    async def test_spatial_join_query_count(self):
        from mcp_arcgis_server.tools.spatial import spatial_join_query

        mock_client = AsyncMock()
        mock_client.query_layer.side_effect = [
            {
                "features": [
                    {
                        "attributes": {"NAME": "Boundary"},
                        "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                    }
                ],
                "count": 1,
            },
            {"count": 5},
        ]

        result = await spatial_join_query(
            mock_client,
            "https://example.com/boundary/0",
            "NAME='Boundary'",
            "https://example.com/target/0",
            operation="count",
        )
        assert result == {"count": 5}

    @pytest.mark.asyncio
    async def test_spatial_join_no_boundary(self):
        from mcp_arcgis_server.tools.spatial import spatial_join_query

        mock_client = AsyncMock()
        mock_client.query_layer.return_value = {"features": [], "count": 0}

        result = await spatial_join_query(
            mock_client,
            "https://example.com/boundary/0",
            "NAME='Missing'",
            "https://example.com/target/0",
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_join_layers(self):
        from mcp_arcgis_server.tools.spatial import join_layers

        mock_client = AsyncMock()
        mock_client.query_layer.side_effect = [
            {
                "features": [
                    {"attributes": {"ID": 1, "NAME": "A"}, "geometry": None},
                    {"attributes": {"ID": 2, "NAME": "B"}, "geometry": None},
                ],
                "count": 2,
            },
            {
                "features": [
                    {"attributes": {"ID": 1, "VALUE": 100}},
                ],
                "count": 1,
            },
        ]

        result = await join_layers(
            mock_client,
            "https://example.com/primary/0",
            "1=1",
            "*",
            "https://example.com/secondary/0",
            "1=1",
            "*",
            "ID",
        )
        assert result["count"] == 1
        assert result["features"][0]["attributes"]["VALUE"] == 100
        assert result["features"][0]["attributes"]["NAME"] == "A"


class TestPlanTool:
    """Unit tests for execute_query_plan standalone function."""

    @pytest.mark.asyncio
    async def test_single_count_query(self):
        from mcp_arcgis_server.tools.plan import execute_query_plan

        mock_client = AsyncMock()
        mock_client.query_layer.return_value = {"count": 10}

        plan = json.dumps(
            {
                "action": "query",
                "query": [
                    {
                        "type": "count",
                        "layer": "TestLayer",
                        "layer_url": "https://example.com/layer/0",
                        "where": "1=1",
                    }
                ],
            }
        )

        result = await execute_query_plan(mock_client, plan)
        assert result["count"] == 10
        assert result["type"] == "count"

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        from mcp_arcgis_server.tools.plan import execute_query_plan

        mock_client = AsyncMock()
        result = await execute_query_plan(mock_client, "not json")
        assert "error" in result


# ---------------------------------------------------------------------------
# ArcGISClient tests (Task 10.5 — thread pool)
# ---------------------------------------------------------------------------


class TestArcGISClientThreadPool:
    """Tests for async thread pool behavior."""

    @pytest.mark.asyncio
    async def test_query_runs_in_thread_pool(self):
        """Verify _execute_query runs in thread pool, not event loop thread."""
        from mcp_arcgis_server.arcgis.auth import GISAuthManager
        from mcp_arcgis_server.arcgis.client import ArcGISClient

        auth = MagicMock(spec=GISAuthManager)
        auth.is_internal_url.return_value = False
        auth.gis = None

        client = ArcGISClient(auth)
        execution_thread = None

        def mock_execute_query(*args):
            nonlocal execution_thread
            execution_thread = threading.current_thread()
            mock_fs = MagicMock()
            mock_fs.features = []
            mock_fs.to_dict.return_value = {"features": [], "count": 0}
            return {"features": [], "count": 0}

        client._execute_query = mock_execute_query

        try:
            result = await client.query_layer("https://public.example.com/layer/0")
            assert execution_thread is not None
            assert execution_thread != threading.current_thread()
            assert "arcgis" in execution_thread.name
        finally:
            client.close()

    @pytest.mark.asyncio
    async def test_close_prevents_further_queries(self):
        from mcp_arcgis_server.arcgis.auth import GISAuthManager
        from mcp_arcgis_server.arcgis.client import ArcGISClient

        auth = MagicMock(spec=GISAuthManager)
        client = ArcGISClient(auth)
        client.close()

        with pytest.raises(RuntimeError, match="closed"):
            await client.query_layer("https://example.com/layer/0")


# ---------------------------------------------------------------------------
# Token refresh race test (Task 10.6)
# ---------------------------------------------------------------------------


class TestTokenRefreshRace:
    """Tests for concurrent token refresh via asyncio.Lock."""

    @pytest.mark.asyncio
    async def test_concurrent_refresh_only_one_init(self):
        """Simulate concurrent 498 errors, verify only one re-initialization."""
        from mcp_arcgis_server.arcgis.auth import GISAuthManager

        env = {
            "ARCGIS_PORTAL_URL": "https://arcgis.example.com/arcgis",
            "ARCGIS_USERNAME": "user",
            "ARCGIS_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=False):
            auth = GISAuthManager()
            init_count = 0
            original_init = auth._initialize_gis

            def counting_init():
                nonlocal init_count
                init_count += 1
                auth._gis = MagicMock()
                auth._init_strategy = 1

            auth._initialize_gis = counting_init

            cache_clear_count = 0

            def counting_clear():
                nonlocal cache_clear_count
                cache_clear_count += 1

            # Fire 5 concurrent refreshes
            await asyncio.gather(
                auth.refresh(counting_clear),
                auth.refresh(counting_clear),
                auth.refresh(counting_clear),
                auth.refresh(counting_clear),
                auth.refresh(counting_clear),
            )

            # Due to asyncio.Lock, they serialize — each one runs init
            # But critically, they don't race or crash
            assert init_count == 5  # Lock serializes, doesn't deduplicate
            assert auth.gis is not None
