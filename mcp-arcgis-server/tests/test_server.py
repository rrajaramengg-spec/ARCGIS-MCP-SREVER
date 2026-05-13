"""
Unit tests for mcp-arcgis-server.
Tests ArcGISClient domain-based routing, FeatureSet conversion, MCP tool shapes,
and registry-based tool discovery.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_arcgis_server.config import ServerConfig


# ---------------------------------------------------------------------------
# ArcGISClient tests
# ---------------------------------------------------------------------------


class TestArcGISClient:
    """Tests for ArcGISClient domain-based URL routing and GIS initialization."""

    def test_internal_url_gets_gis(self):
        """Internal URL matching portal domain gets authenticated FeatureLayer."""
        config = ServerConfig(
            portal_url="https://arcgis.example.com/arcgis",
            username="user",
            password="pass",
        )
        with patch("mcp_arcgis_server.arcgis.auth.GIS") as mock_gis_cls:
            mock_gis_cls.return_value = MagicMock()
            with patch("mcp_arcgis_server.arcgis.client.FeatureLayer") as mock_fl_cls:
                from mcp_arcgis_server.arcgis.auth import GISAuthManager
                from mcp_arcgis_server.arcgis.client import ArcGISClient

                auth = GISAuthManager(config)
                # Simulate successful init
                auth._gis = mock_gis_cls.return_value
                client = ArcGISClient(auth, config)
                client._get_feature_layer(
                    "https://arcgis.example.com/server/rest/services/Svc/MapServer/0"
                )
                mock_fl_cls.assert_called_once()
                call_kwargs = mock_fl_cls.call_args
                assert call_kwargs[1].get("gis") is not None

    def test_external_url_no_gis(self):
        """External URL gets anonymous FeatureLayer (no GIS)."""
        config = ServerConfig(
            portal_url="https://arcgis.example.com/arcgis",
            username="user",
            password="pass",
        )
        with patch("mcp_arcgis_server.arcgis.auth.GIS"):
            with patch("mcp_arcgis_server.arcgis.client.FeatureLayer") as mock_fl_cls:
                from mcp_arcgis_server.arcgis.auth import GISAuthManager
                from mcp_arcgis_server.arcgis.client import ArcGISClient

                auth = GISAuthManager(config)
                client = ArcGISClient(auth, config)
                client._get_feature_layer(
                    "https://services.arcgis.com/public/FeatureServer/0"
                )
                mock_fl_cls.assert_called_once_with(
                    "https://services.arcgis.com/public/FeatureServer/0"
                )

    def test_case_insensitive_hostname(self):
        """Hostname comparison is case-insensitive."""
        config = ServerConfig(
            portal_url="https://ARCGIS.Example.COM/arcgis",
            username="user",
            password="pass",
        )
        from mcp_arcgis_server.arcgis.auth import GISAuthManager

        auth = GISAuthManager(config)
        assert auth.is_internal_url(
            "https://arcgis.example.com/server/rest/layer/0"
        )

    def test_no_portal_url(self):
        """No portal URL configured — all URLs treated as external."""
        config = ServerConfig(portal_url="")
        from mcp_arcgis_server.arcgis.auth import GISAuthManager

        auth = GISAuthManager(config)
        assert not auth.is_internal_url("https://any.server.com/layer/0")


class TestFeatureSetConversion:
    """Tests for FeatureSet to ArcGIS standard dict conversion."""

    def test_featureset_to_dict(self):
        """featureset_to_dict produces ArcGIS standard output via to_dict()."""
        from mcp_arcgis_server.arcgis.geometry import featureset_to_dict

        mock_fs = MagicMock()
        mock_fs.features = [MagicMock(), MagicMock()]
        mock_fs.to_dict.return_value = {
            "objectIdFieldName": "OBJECTID",
            "geometryType": "esriGeometryPolygon",
            "spatialReference": {"wkid": 4326},
            "fields": [
                {"name": "NAME", "type": "esriFieldTypeString", "alias": "Name"},
                {"name": "STATUS", "type": "esriFieldTypeString", "alias": "Status"},
            ],
            "features": [
                {"attributes": {"NAME": "Test", "STATUS": "Active"}, "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
                {"attributes": {"NAME": "Other", "STATUS": "Inactive"}, "geometry": None},
            ],
        }

        result = featureset_to_dict(mock_fs)

        assert result["count"] == 2
        assert len(result["features"]) == 2
        assert result["features"][0]["attributes"]["NAME"] == "Test"
        assert result["features"][0]["geometry"] == {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        assert result["features"][1]["geometry"] is None
        assert result["geometryType"] == "esriGeometryPolygon"
        assert result["spatialReference"] == {"wkid": 4326}
        assert result["objectIdFieldName"] == "OBJECTID"
        assert len(result["fields"]) == 2

    def test_featureset_to_dict_empty(self):
        """Empty FeatureSet produces empty result with count 0."""
        from mcp_arcgis_server.arcgis.geometry import featureset_to_dict

        mock_fs = MagicMock()
        mock_fs.features = []
        mock_fs.to_dict.return_value = {"features": []}

        result = featureset_to_dict(mock_fs)
        assert result["count"] == 0
        assert result["features"] == []


class TestGeometryFilter:
    """Tests for build_geometry_filter."""

    def test_intersects_filter(self):
        """Intersects spatial rel calls geometry_filters.intersects."""
        with patch("mcp_arcgis_server.arcgis.geometry.Geometry") as mock_geom:
            with patch("mcp_arcgis_server.arcgis.geometry.geometry_filters") as mock_filters:
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
        """Contains spatial rel calls geometry_filters.contains."""
        with patch("mcp_arcgis_server.arcgis.geometry.Geometry") as mock_geom:
            with patch("mcp_arcgis_server.arcgis.geometry.geometry_filters") as mock_filters:
                mock_geom.return_value = "geom_obj"
                mock_filters.contains.return_value = {"filter": "contains"}

                from mcp_arcgis_server.arcgis.geometry import build_geometry_filter

                result = build_geometry_filter(
                    {"x": 0, "y": 0}, "esriSpatialRelContains"
                )
                mock_filters.contains.assert_called_once()

    def test_within_filter(self):
        """Within spatial rel calls geometry_filters.within."""
        with patch("mcp_arcgis_server.arcgis.geometry.Geometry") as mock_geom:
            with patch("mcp_arcgis_server.arcgis.geometry.geometry_filters") as mock_filters:
                mock_geom.return_value = "geom_obj"
                mock_filters.within.return_value = {"filter": "within"}

                from mcp_arcgis_server.arcgis.geometry import build_geometry_filter

                result = build_geometry_filter(
                    {"x": 0, "y": 0}, "esriSpatialRelWithin"
                )
                mock_filters.within.assert_called_once()


class TestFeatureLayerCaching:
    """Tests for FeatureLayer caching via BoundedLayerCache."""

    def test_same_url_returns_cached_instance(self):
        """Repeated calls with same URL return the same FeatureLayer."""
        config = ServerConfig(portal_url="")
        with patch("mcp_arcgis_server.arcgis.client.FeatureLayer") as mock_fl_cls:
            mock_fl_cls.return_value = MagicMock()
            from mcp_arcgis_server.arcgis.auth import GISAuthManager
            from mcp_arcgis_server.arcgis.client import ArcGISClient

            auth = GISAuthManager(config)
            client = ArcGISClient(auth, config)
            fl1 = client._get_feature_layer("https://test/layer/0")
            fl2 = client._get_feature_layer("https://test/layer/0")
            assert fl1 is fl2
            assert mock_fl_cls.call_count == 1

    def test_different_urls_create_separate_instances(self):
        """Different URLs create separate FeatureLayer instances."""
        config = ServerConfig(portal_url="")
        with patch("mcp_arcgis_server.arcgis.client.FeatureLayer") as mock_fl_cls:
            mock_fl_cls.side_effect = [MagicMock(), MagicMock()]
            from mcp_arcgis_server.arcgis.auth import GISAuthManager
            from mcp_arcgis_server.arcgis.client import ArcGISClient

            auth = GISAuthManager(config)
            client = ArcGISClient(auth, config)
            fl1 = client._get_feature_layer("https://test/layer/0")
            fl2 = client._get_feature_layer("https://test/layer/1")
            assert fl1 is not fl2
            assert mock_fl_cls.call_count == 2


class TestResultCap:
    """Tests for 200-feature result cap enforcement."""

    @pytest.mark.asyncio
    async def test_default_cap_2000(self):
        """No result_record_count specified defaults to 2000."""
        config = ServerConfig(portal_url="")
        with patch("mcp_arcgis_server.arcgis.client.FeatureLayer") as mock_fl_cls:
            mock_fl = MagicMock()
            mock_fs = MagicMock()
            mock_fs.features = []
            mock_fs.to_dict.return_value = {"features": []}
            mock_fl.query.return_value = mock_fs
            mock_fl_cls.return_value = mock_fl

            from mcp_arcgis_server.arcgis.auth import GISAuthManager
            from mcp_arcgis_server.arcgis.client import ArcGISClient

            auth = GISAuthManager(config)
            client = ArcGISClient(auth, config)
            await client.query_layer("https://test/layer/0")
            call_kwargs = mock_fl.query.call_args[1]
            assert call_kwargs["result_record_count"] == 2000

    @pytest.mark.asyncio
    async def test_cap_exceeding_value(self):
        """result_record_count > 2000 is capped to 2000."""
        config = ServerConfig(portal_url="")
        with patch("mcp_arcgis_server.arcgis.client.FeatureLayer") as mock_fl_cls:
            mock_fl = MagicMock()
            mock_fs = MagicMock()
            mock_fs.features = []
            mock_fs.to_dict.return_value = {"features": []}
            mock_fl.query.return_value = mock_fs
            mock_fl_cls.return_value = mock_fl

            from mcp_arcgis_server.arcgis.auth import GISAuthManager
            from mcp_arcgis_server.arcgis.client import ArcGISClient

            auth = GISAuthManager(config)
            client = ArcGISClient(auth, config)
            await client.query_layer(
                "https://test/layer/0", result_record_count=5000
            )
            call_kwargs = mock_fl.query.call_args[1]
            assert call_kwargs["result_record_count"] == 2000

    @pytest.mark.asyncio
    async def test_below_cap_passes_through(self):
        """result_record_count < 2000 passes through unchanged."""
        config = ServerConfig(portal_url="")
        with patch("mcp_arcgis_server.arcgis.client.FeatureLayer") as mock_fl_cls:
            mock_fl = MagicMock()
            mock_fs = MagicMock()
            mock_fs.features = []
            mock_fs.to_dict.return_value = {"features": []}
            mock_fl.query.return_value = mock_fs
            mock_fl_cls.return_value = mock_fl

            from mcp_arcgis_server.arcgis.auth import GISAuthManager
            from mcp_arcgis_server.arcgis.client import ArcGISClient

            auth = GISAuthManager(config)
            client = ArcGISClient(auth, config)
            await client.query_layer(
                "https://test/layer/0", result_record_count=50
            )
            call_kwargs = mock_fl.query.call_args[1]
            assert call_kwargs["result_record_count"] == 50


# ---------------------------------------------------------------------------
# Tool response shape tests (direct function calls with mock client)
# ---------------------------------------------------------------------------


class TestToolResponseShapes:
    """Tests that tool responses match expected structure."""

    @pytest.mark.asyncio
    async def test_query_features_error_propagates(self):
        """query_features raises on client failure (error handling is in wrapper)."""
        from mcp_arcgis_server.tools.query import query_features

        mock_client = AsyncMock()
        mock_client.query_layer = AsyncMock(
            side_effect=Exception("connection error")
        )
        with pytest.raises(Exception, match="connection error"):
            await query_features(mock_client, layer_url="https://bad.url/layer/0")

    @pytest.mark.asyncio
    async def test_count_features_shape(self):
        """count_features returns {count: int}."""
        from mcp_arcgis_server.tools.query import count_features

        mock_client = AsyncMock()
        mock_client.query_layer = AsyncMock(return_value={"count": 42})
        result = await count_features(mock_client, layer_url="https://test/layer/0", where="1=1")
        assert result == {"count": 42}

    @pytest.mark.asyncio
    async def test_spatial_join_no_boundary(self):
        """spatial_join_query returns error when no boundary features found."""
        from mcp_arcgis_server.tools.spatial import spatial_join_query

        mock_client = AsyncMock()
        mock_client.query_layer = AsyncMock(return_value={"features": []})
        result = await spatial_join_query(
            mock_client,
            boundary_layer_url="https://test/boundary/0",
            boundary_where="NAME='nonexistent'",
            target_layer_url="https://test/target/0",
        )
        assert "error" in result
        assert "No boundary features found" in result["error"]

    @pytest.mark.asyncio
    async def test_join_layers_shape(self):
        """join_layers returns {type, features, count}."""
        from mcp_arcgis_server.tools.spatial import join_layers

        mock_client = AsyncMock()
        mock_client.query_layer = AsyncMock(
            side_effect=[
                {"features": [{"attributes": {"ID": 1, "name": "A"}}]},
                {"features": [{"attributes": {"ID": 1, "value": 100}}]},
            ]
        )
        result = await join_layers(
            mock_client,
            primary_layer_url="https://test/primary/0",
            secondary_layer_url="https://test/secondary/0",
            join_field="ID",
        )
        assert result["type"] == "joined_features"
        assert result["count"] == 1
        assert result["features"][0]["attributes"]["name"] == "A"
        assert result["features"][0]["attributes"]["value"] == 100

    @pytest.mark.asyncio
    async def test_join_layers_no_match(self):
        """join_layers returns empty when no matching join values."""
        from mcp_arcgis_server.tools.spatial import join_layers

        mock_client = AsyncMock()
        mock_client.query_layer = AsyncMock(
            side_effect=[
                {"features": [{"attributes": {"ID": 1}}]},
                {"features": [{"attributes": {"ID": 999}}]},
            ]
        )
        result = await join_layers(
            mock_client,
            primary_layer_url="https://test/primary/0",
            secondary_layer_url="https://test/secondary/0",
            join_field="ID",
        )
        assert result["type"] == "joined_features"
        assert result["count"] == 0
        assert result["features"] == []


# ---------------------------------------------------------------------------
# Geometry union tests
# ---------------------------------------------------------------------------


class TestUnionFeatureGeometries:
    """Tests for union_feature_geometries utility in arcgis/geometry.py."""

    def _poly(self, ring_id=0):
        """Helper to create a polygon geometry dict."""
        return {
            "rings": [[[ring_id, 0], [ring_id, 1], [ring_id + 1, 1], [ring_id + 1, 0], [ring_id, 0]]],
            "spatialReference": {"wkid": 4326},
        }

    def test_empty_list_returns_none(self):
        """Empty feature list returns None."""
        from mcp_arcgis_server.arcgis.geometry import union_feature_geometries

        assert union_feature_geometries([]) is None

    def test_no_geometry_returns_none(self):
        """Features with no geometry key return None."""
        from mcp_arcgis_server.arcgis.geometry import union_feature_geometries

        features = [{"attributes": {"id": 1}}, {"attributes": {"id": 2}}]
        assert union_feature_geometries(features) is None

    def test_single_feature_returns_geometry_directly(self):
        """Single feature returns its geometry without calling union."""
        from mcp_arcgis_server.arcgis.geometry import union_feature_geometries

        geom = self._poly()
        features = [{"attributes": {"id": 1}, "geometry": geom}]

        with patch("mcp_arcgis_server.arcgis.geometry.geo_union") as mock_union:
            result = union_feature_geometries(features)
            mock_union.assert_not_called()
            assert result is geom

    def test_multiple_features_uses_ring_merge(self):
        """Multiple features uses client-side ring merge (instant, no server call)."""
        from mcp_arcgis_server.arcgis.geometry import union_feature_geometries

        geom1 = self._poly(0)
        geom2 = self._poly(1)
        features = [
            {"attributes": {"id": 1}, "geometry": geom1},
            {"attributes": {"id": 2}, "geometry": geom2},
        ]

        with patch("mcp_arcgis_server.arcgis.geometry.geo_union") as mock_union:
            result = union_feature_geometries(features)
        # Ring merge is used — geo_union is NOT called
        mock_union.assert_not_called()
        assert result is not None
        assert "rings" in result
        assert len(result["rings"]) == 2

    def test_filters_features_without_geometry(self):
        """Features without geometry are filtered out."""
        from mcp_arcgis_server.arcgis.geometry import union_feature_geometries

        geom = self._poly()
        features = [
            {"attributes": {"id": 1}},  # no geometry
            {"attributes": {"id": 2}, "geometry": geom},
            {"attributes": {"id": 3}, "geometry": None},  # None geometry
        ]
        result = union_feature_geometries(features)
        # Single valid geometry → returned directly
        assert result is geom

    def test_mixed_geometry_types_raises(self):
        """Mixed geometry types raises ValueError."""
        from mcp_arcgis_server.arcgis.geometry import union_feature_geometries

        features = [
            {"geometry": {"x": 1, "y": 2, "spatialReference": {"wkid": 4326}}},
            {"geometry": self._poly()},
        ]
        with pytest.raises(ValueError, match="Cannot union mixed geometry types"):
            union_feature_geometries(features)

    def test_truncates_at_500(self):
        """More than 500 features are truncated with warning."""
        from mcp_arcgis_server.arcgis.geometry import union_feature_geometries

        features = [{"geometry": self._poly(i)} for i in range(600)]

        with patch("mcp_arcgis_server.arcgis.geometry.logger") as mock_logger:
            result = union_feature_geometries(features)
            mock_logger.warning.assert_called_once()
            assert "600" in str(mock_logger.warning.call_args)
            assert "500" in str(mock_logger.warning.call_args)
        # Ring merge used — result should have 500 rings (one per polygon)
        assert result is not None
        assert "rings" in result
        assert len(result["rings"]) == 500

    def test_ring_merge_produces_correct_output(self):
        """Ring merge combines polygon rings from multiple features."""
        from mcp_arcgis_server.arcgis.geometry import (
            union_feature_geometries,
        )

        geom1 = self._poly(0)
        geom2 = self._poly(1)
        features = [
            {"attributes": {"id": 1}, "geometry": geom1},
            {"attributes": {"id": 2}, "geometry": geom2},
        ]

        result = union_feature_geometries(features)

        assert result is not None
        assert "rings" in result
        # Should contain rings from both geometries
        assert len(result["rings"]) == 2
        assert result["spatialReference"]["wkid"] == 4326


# ---------------------------------------------------------------------------
# Union geometries MCP tool tests
# ---------------------------------------------------------------------------


class TestUnionGeometriesTool:
    """Tests for the union_geometries MCP tool."""

    @pytest.mark.asyncio
    async def test_valid_multi_geometry(self):
        """Valid multi-geometry JSON calls client.union_geometries."""
        from mcp_arcgis_server.tools.geometry_ops import union_geometries
        import json

        geom1 = {"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]], "spatialReference": {"wkid": 4326}}
        geom2 = {"rings": [[[1, 0], [1, 1], [2, 1], [2, 0], [1, 0]]], "spatialReference": {"wkid": 4326}}
        unified = {"rings": [[[0, 0], [0, 1], [2, 1], [2, 0], [0, 0]]], "spatialReference": {"wkid": 4326}}

        mock_client = AsyncMock()
        mock_client.union_geometries = AsyncMock(return_value=unified)

        result = await union_geometries(mock_client, geometries=json.dumps([geom1, geom2]))
        assert result == {"geometry": unified}
        mock_client.union_geometries.assert_awaited_once_with([geom1, geom2])

    @pytest.mark.asyncio
    async def test_single_geometry(self):
        """Single geometry returns it directly via client."""
        from mcp_arcgis_server.tools.geometry_ops import union_geometries
        import json

        geom = {"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]], "spatialReference": {"wkid": 4326}}
        mock_client = AsyncMock()
        mock_client.union_geometries = AsyncMock(return_value=geom)

        result = await union_geometries(mock_client, geometries=json.dumps([geom]))
        assert result == {"geometry": geom}

    @pytest.mark.asyncio
    async def test_empty_array(self):
        """Empty JSON array returns error."""
        from mcp_arcgis_server.tools.geometry_ops import union_geometries

        mock_client = AsyncMock()
        result = await union_geometries(mock_client, geometries="[]")
        assert "error" in result
        assert result["error"] == "No geometries provided"

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        """Invalid JSON returns error."""
        from mcp_arcgis_server.tools.geometry_ops import union_geometries

        mock_client = AsyncMock()
        result = await union_geometries(mock_client, geometries="not-json")
        assert "error" in result
        assert result["error"] == "Invalid geometry JSON"


# ---------------------------------------------------------------------------
# execute_query_plan multi-feature parent tests
# ---------------------------------------------------------------------------


class TestExecuteQueryPlanUnion:
    """Tests for execute_query_plan with multi-feature parent geometry union."""

    @pytest.mark.asyncio
    async def test_multi_feature_parent_unions_geometry(self):
        """Parent query returning 2+ features unions geometries for child spatial filter."""
        from mcp_arcgis_server.tools.plan import execute_query_plan
        import json

        parent_geom1 = {"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]], "spatialReference": {"wkid": 4326}}
        parent_geom2 = {"rings": [[[1, 0], [1, 1], [2, 1], [2, 0], [1, 0]]], "spatialReference": {"wkid": 4326}}
        unified_geom = {"rings": [[[0, 0], [0, 1], [2, 1], [2, 0], [0, 0]]], "spatialReference": {"wkid": 4326}}

        mock_client = AsyncMock()
        mock_client.query_layer = AsyncMock(return_value={
            "features": [
                {"attributes": {"NAME": "County1"}, "geometry": parent_geom1},
                {"attributes": {"NAME": "County2"}, "geometry": parent_geom2},
            ],
            "count": 2,
        })
        mock_client.spatial_query = AsyncMock(return_value={
            "features": [{"attributes": {"PSAP": "Station1"}}],
            "count": 1,
        })

        plan = {
            "action": "query",
            "query": [{
                "type": "where",
                "layer": "Counties",
                "layer_url": "https://test/counties/0",
                "where": "STATE='CO'",
                "fields": ["NAME"],
                "children": [{
                    "type": "where",
                    "layer": "PSAPs",
                    "layer_url": "https://test/psaps/0",
                    "where": "1=1",
                    "fields": ["PSAP"],
                }],
            }],
        }

        with patch("mcp_arcgis_server.tools.plan.union_feature_geometries", return_value=unified_geom) as mock_union:
            result = await execute_query_plan(mock_client, query_plan=json.dumps(plan))

        mock_union.assert_called_once()
        # Verify the child spatial_query was called with the unified geometry
        mock_client.spatial_query.assert_awaited_once()
        call_kwargs = mock_client.spatial_query.call_args
        assert call_kwargs[1]["geometry"] is unified_geom

    @pytest.mark.asyncio
    async def test_parent_no_geometry_returns_error(self):
        """Parent features with no geometry returns error."""
        from mcp_arcgis_server.tools.plan import execute_query_plan
        import json

        mock_client = AsyncMock()
        mock_client.query_layer = AsyncMock(return_value={
            "features": [{"attributes": {"NAME": "County1"}}],  # no geometry
            "count": 1,
        })

        plan = {
            "action": "query",
            "query": [{
                "type": "where",
                "layer": "Counties",
                "layer_url": "https://test/counties/0",
                "where": "NAME='X'",
                "children": [{"type": "where", "layer": "PSAPs", "layer_url": "https://test/psaps/0"}],
            }],
        }

        with patch("mcp_arcgis_server.tools.plan.union_feature_geometries", return_value=None):
            result = await execute_query_plan(mock_client, query_plan=json.dumps(plan))

        assert "error" in result
        assert "no geometry" in result["error"].lower()


# ---------------------------------------------------------------------------
# Registry-based tool discovery tests
# ---------------------------------------------------------------------------


EXPECTED_TOOL_NAMES = {
    "query_features",
    "count_features",
    "spatial_join_query",
    "join_layers",
    "execute_query_plan",
    "search_content",
    "search_layers",
    "summarize_field",
    "get_feature_table",
    "buffer_and_query",
    "find_nearby",
    "geocode",
    "reversegeocode",
    "union_geometries",
}


class TestToolRegistry:
    """Tests for registry-based tool discovery via create_server."""

    def test_14_tools_discovered(self):
        """All 14 tools are discovered via get_registered_tools."""
        from mcp_arcgis_server.tools._registry import (
            _auto_import_tool_modules,
            get_registered_tools,
        )

        _auto_import_tool_modules()
        tools = get_registered_tools()
        tool_names = {t.name for t in tools}
        assert tool_names >= EXPECTED_TOOL_NAMES, (
            f"Missing tools: {EXPECTED_TOOL_NAMES - tool_names}"
        )

    def test_tool_names_match_prerefactor(self):
        """Registered tool names match pre-refactor names exactly."""
        from mcp_arcgis_server.tools._registry import (
            _auto_import_tool_modules,
            get_registered_tools,
        )

        _auto_import_tool_modules()
        tools = get_registered_tools()
        tool_names = {t.name for t in tools}
        for name in EXPECTED_TOOL_NAMES:
            assert name in tool_names, f"Tool '{name}' not found in registry"

    def test_all_tools_have_descriptions(self):
        """All registered tools have non-empty descriptions."""
        from mcp_arcgis_server.tools._registry import (
            _auto_import_tool_modules,
            get_registered_tools,
        )

        _auto_import_tool_modules()
        tools = get_registered_tools()
        for tool in tools:
            if tool.name in EXPECTED_TOOL_NAMES:
                assert tool.description, f"Tool '{tool.name}' has no description"

    def test_discover_and_register_with_mock_mcp(self):
        """discover_and_register registers all tools on a mock FastMCP."""
        from mcp_arcgis_server.tools._registry import (
            _TOOL_REGISTRY,
            discover_and_register,
        )

        saved = list(_TOOL_REGISTRY)
        try:
            mock_mcp = MagicMock()
            mock_client = AsyncMock()
            mock_config = MagicMock()
            mock_config.disabled_tools_list = []

            count = discover_and_register(mock_mcp, mock_client, mock_config)
            assert count >= 14
            assert mock_mcp.add_tool.call_count >= 13
        finally:
            _TOOL_REGISTRY.clear()
            _TOOL_REGISTRY.extend(saved)

    def test_tool_disable_filtering(self):
        """Disabled tools are not registered."""
        from mcp_arcgis_server.tools._registry import (
            _TOOL_REGISTRY,
            discover_and_register,
        )

        saved = list(_TOOL_REGISTRY)
        try:
            mock_mcp = MagicMock()
            mock_client = AsyncMock()
            mock_config = MagicMock()
            mock_config.disabled_tools_list = ["geocode", "reversegeocode"]

            count = discover_and_register(mock_mcp, mock_client, mock_config)
            registered_names = [
                call[1].get("name", call[0][1] if len(call[0]) > 1 else None)
                for call in mock_mcp.add_tool.call_args_list
            ]
            assert "geocode" not in registered_names
            assert "reversegeocode" not in registered_names
            assert count >= 12  # 14 - 2 disabled
        finally:
            _TOOL_REGISTRY.clear()
            _TOOL_REGISTRY.extend(saved)
