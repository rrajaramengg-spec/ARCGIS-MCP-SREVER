"""Unit tests for GraphContext, ArtifactType, ArtifactMeta, and NodeTiming."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.orchestrator.graph.context import (
    ArtifactMeta,
    ArtifactNotFoundError,
    ArtifactType,
    GraphContext,
    NodeTiming,
)
from core.orchestrator.graph.resilience import RetryBudget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(**overrides) -> GraphContext:
    defaults = {
        "correlation_id": "test-corr-id",
        "mcp_client": AsyncMock(),
        "retry_budget": RetryBudget(max_retries=5),
    }
    defaults.update(overrides)
    return GraphContext(**defaults)


# ---------------------------------------------------------------------------
# ArtifactType
# ---------------------------------------------------------------------------


class TestArtifactType:
    def test_members(self):
        assert ArtifactType.GEOMETRY == "GEOMETRY"
        assert ArtifactType.FEATURE_SET == "FEATURE_SET"
        assert ArtifactType.BUFFER_ZONE == "BUFFER_ZONE"
        assert ArtifactType.COUNT == "COUNT"
        assert ArtifactType.SUMMARY == "SUMMARY"
        assert ArtifactType.UNION_GEOMETRY == "UNION_GEOMETRY"


# ---------------------------------------------------------------------------
# ArtifactMeta
# ---------------------------------------------------------------------------


class TestArtifactMeta:
    def test_frozen(self):
        meta = ArtifactMeta(
            producer_node_id="n1",
            artifact_type=ArtifactType.GEOMETRY,
        )
        with pytest.raises(AttributeError):
            meta.producer_node_id = "n2"  # type: ignore[misc]

    def test_created_at_populated(self):
        meta = ArtifactMeta(
            producer_node_id="n1",
            artifact_type=ArtifactType.GEOMETRY,
        )
        assert meta.created_at > 0


# ---------------------------------------------------------------------------
# NodeTiming
# ---------------------------------------------------------------------------


class TestNodeTiming:
    def test_defaults(self):
        t = NodeTiming(node_id="n1", node_type="geocode")
        assert t.ms == 0.0
        assert t.retries == 0
        assert t.status == "success"

    def test_custom_values(self):
        t = NodeTiming(
            node_id="n1",
            node_type="query",
            ms=150.5,
            retries=2,
            status="error",
        )
        assert t.ms == 150.5
        assert t.retries == 2
        assert t.status == "error"


# ---------------------------------------------------------------------------
# GraphContext — put / get
# ---------------------------------------------------------------------------


class TestGraphContextArtifacts:
    def test_put_and_get(self):
        ctx = _make_ctx()
        ctx.put("geom_1", {"x": 1, "y": 2}, ArtifactType.GEOMETRY, "n1")
        assert ctx.get("geom_1") == {"x": 1, "y": 2}

    def test_get_missing_raises(self):
        ctx = _make_ctx()
        with pytest.raises(ArtifactNotFoundError, match="no_such_key"):
            ctx.get("no_such_key")

    def test_lineage_tracking(self):
        ctx = _make_ctx()
        ctx.put("feat_1", [1, 2, 3], ArtifactType.FEATURE_SET, "n2")
        meta = ctx.artifact_meta["feat_1"]
        assert meta.producer_node_id == "n2"
        assert meta.artifact_type == ArtifactType.FEATURE_SET
        assert meta.created_at > 0

    def test_overwrite_artifact(self):
        ctx = _make_ctx()
        ctx.put("key", "v1", ArtifactType.GEOMETRY, "n1")
        ctx.put("key", "v2", ArtifactType.BUFFER_ZONE, "n2")
        assert ctx.get("key") == "v2"
        assert ctx.artifact_meta["key"].producer_node_id == "n2"

    def test_multiple_artifacts(self):
        ctx = _make_ctx()
        ctx.put("a", 1, ArtifactType.GEOMETRY, "n1")
        ctx.put("b", 2, ArtifactType.COUNT, "n2")
        ctx.put("c", 3, ArtifactType.SUMMARY, "n3")
        assert len(ctx.artifacts) == 3
        assert len(ctx.artifact_meta) == 3

    def test_error_message_lists_available_keys(self):
        ctx = _make_ctx()
        ctx.put("exists", {}, ArtifactType.GEOMETRY, "n1")
        with pytest.raises(ArtifactNotFoundError, match="exists"):
            ctx.get("missing")


# ---------------------------------------------------------------------------
# GraphContext — construction
# ---------------------------------------------------------------------------


class TestGraphContextConstruction:
    def test_empty_initial_state(self):
        ctx = _make_ctx()
        assert ctx.artifacts == {}
        assert ctx.artifact_meta == {}
        assert ctx.node_timing == []

    def test_correlation_id(self):
        ctx = _make_ctx(correlation_id="req-123")
        assert ctx.correlation_id == "req-123"

    def test_retry_budget_shared(self):
        budget = RetryBudget(max_retries=3)
        ctx = _make_ctx(retry_budget=budget)
        ctx.retry_budget.record_retry()
        assert budget.used == 1

    def test_progress_callback_default_none(self):
        ctx = _make_ctx()
        assert ctx.progress_callback is None

    def test_semaphore_default_none(self):
        ctx = _make_ctx()
        assert ctx.semaphore is None

    def test_semaphore_injection(self):
        sem = asyncio.Semaphore(5)
        ctx = _make_ctx(semaphore=sem)
        assert ctx.semaphore is sem


# ---------------------------------------------------------------------------
# GraphContext — shared state in asyncio.gather
# ---------------------------------------------------------------------------


class TestGraphContextSharedState:
    @pytest.mark.asyncio
    async def test_parallel_writes_visible(self):
        """Verify that parallel tasks writing to the same GraphContext
        instance produce artifacts visible to the parent and siblings."""
        ctx = _make_ctx()

        async def writer(key: str, value: Any):
            ctx.put(key, value, ArtifactType.GEOMETRY, key)

        await asyncio.gather(
            writer("a", 1),
            writer("b", 2),
            writer("c", 3),
        )

        assert ctx.get("a") == 1
        assert ctx.get("b") == 2
        assert ctx.get("c") == 3
        assert len(ctx.artifact_meta) == 3


# We need Any for the type hint in the test helper above.
from typing import Any  # noqa: E402
