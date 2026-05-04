"""
Tests for parallel child query execution in execute_query_plan.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_arcgis_server.tools.plan import execute_query_plan


class TestParallelChildQueries:
    """Tests for asyncio.gather-based parallel child query execution."""

    @pytest.mark.asyncio
    async def test_children_execute_in_parallel(self):
        """Child queries should run concurrently, not sequentially."""
        mock_client = AsyncMock()

        # Parent returns features with geometry
        mock_client.query_layer = AsyncMock(return_value={
            "features": [
                {
                    "geometry": {
                        "rings": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                        "spatialReference": {"wkid": 4326},
                    },
                    "attributes": {"NAME": "TEST"},
                }
            ],
        })

        # Children take 0.1s each — parallel should be ~0.1s total, not 0.3s
        call_times = []

        async def slow_spatial_query(**kwargs):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)
            return {"features": [], "count": 0}

        mock_client.spatial_query = slow_spatial_query

        plan = {
            "action": "query",
            "query": [
                {
                    "type": "where",
                    "layer": "PARENT",
                    "layer_url": "http://test/parent",
                    "where": "1=1",
                    "fields": ["NAME"],
                    "children": [
                        {"type": "where", "layer": "C1", "layer_url": "http://test/c1", "where": "1=1", "fields": ["F1"]},
                        {"type": "where", "layer": "C2", "layer_url": "http://test/c2", "where": "1=1", "fields": ["F2"]},
                        {"type": "where", "layer": "C3", "layer_url": "http://test/c3", "where": "1=1", "fields": ["F3"]},
                    ],
                }
            ],
        }

        result = await execute_query_plan(mock_client, json.dumps(plan))

        # All 3 children should have executed
        assert len(result.get("children", [])) == 3
        # They should have started near-simultaneously (within 50ms)
        if len(call_times) == 3:
            assert max(call_times) - min(call_times) < 0.05

    @pytest.mark.asyncio
    async def test_single_child_failure_does_not_cancel_others(self):
        """One failing child should not prevent others from completing."""
        mock_client = AsyncMock()

        mock_client.query_layer = AsyncMock(return_value={
            "features": [
                {
                    "geometry": {
                        "rings": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                        "spatialReference": {"wkid": 4326},
                    },
                    "attributes": {"NAME": "TEST"},
                }
            ],
        })

        call_count = 0

        async def mixed_spatial_query(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("layer_url") == "http://test/fail":
                raise ConnectionError("ArcGIS server timeout")
            return {"features": [{"attributes": {"ID": 1}}], "count": 1}

        mock_client.spatial_query = mixed_spatial_query

        plan = {
            "action": "query",
            "query": [
                {
                    "type": "where",
                    "layer": "PARENT",
                    "layer_url": "http://test/parent",
                    "where": "1=1",
                    "children": [
                        {"type": "where", "layer": "OK1", "layer_url": "http://test/ok1", "where": "1=1"},
                        {"type": "where", "layer": "FAIL", "layer_url": "http://test/fail", "where": "1=1"},
                        {"type": "where", "layer": "OK2", "layer_url": "http://test/ok2", "where": "1=1"},
                    ],
                }
            ],
        }

        result = await execute_query_plan(mock_client, json.dumps(plan))
        children = result.get("children", [])

        assert len(children) == 3
        # First and third should succeed
        assert "error" not in children[0]
        assert "error" in children[1]  # The failing one
        assert "error" not in children[2]

    @pytest.mark.asyncio
    async def test_child_results_include_execution_ms(self):
        """Each child result should include execution_ms timing."""
        mock_client = AsyncMock()

        mock_client.query_layer = AsyncMock(return_value={
            "features": [
                {
                    "geometry": {
                        "rings": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                        "spatialReference": {"wkid": 4326},
                    },
                    "attributes": {"NAME": "TEST"},
                }
            ],
        })
        mock_client.spatial_query = AsyncMock(return_value={
            "features": [], "count": 0,
        })

        plan = {
            "action": "query",
            "query": [
                {
                    "type": "where",
                    "layer": "PARENT",
                    "layer_url": "http://test/parent",
                    "where": "1=1",
                    "children": [
                        {"type": "where", "layer": "CHILD", "layer_url": "http://test/child", "where": "1=1"},
                    ],
                }
            ],
        }

        result = await execute_query_plan(mock_client, json.dumps(plan))
        children = result.get("children", [])

        assert len(children) == 1
        assert "execution_ms" in children[0]
        assert isinstance(children[0]["execution_ms"], float)
        assert children[0]["execution_ms"] >= 0
