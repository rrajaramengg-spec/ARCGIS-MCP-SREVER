"""Unit tests for ExecutionGraph, GraphRuntime, and GraphResult."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.graph.context import (
    ArtifactType,
    GraphContext,
    NodeTiming,
)
from core.orchestrator.graph.nodes import (
    BufferNode,
    GeocodeNode,
    QueryNode,
    SpatialJoinNode,
)
from core.orchestrator.graph.resilience import RetryBudget, RetryPolicy
from core.orchestrator.graph.runtime import (
    ExecutionGraph,
    GraphResult,
    GraphRuntime,
    GraphValidationError,
    NodeExecutionError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(**overrides) -> GraphContext:
    defaults = {
        "correlation_id": "test-corr",
        "mcp_client": AsyncMock(),
        "retry_budget": RetryBudget(max_retries=10),
    }
    defaults.update(overrides)
    return GraphContext(**defaults)


def _noop_executor():
    """Executor that stores a dummy value in the artifact store."""

    async def _exec(node, ctx):
        ctx.put(
            node.output_artifact,
            {"result": f"from-{node.node_id}"},
            ArtifactType.GEOMETRY,
            node.node_id,
        )

    return _exec


def _make_executor_map():
    """Create an executor map with noop executors for all node types."""
    exec_fn = _noop_executor()
    return {
        "geocode": exec_fn,
        "query": exec_fn,
        "buffer": exec_fn,
        "spatial_join": exec_fn,
        "union": exec_fn,
        "proximity": exec_fn,
        "summarize": exec_fn,
        "count": exec_fn,
    }


# ---------------------------------------------------------------------------
# Topological Sort Tests
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_linear_chain(self):
        """n1 → n2 → n3 produces three levels."""
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
            "n2": BufferNode(
                node_id="n2", output_artifact="b1",
                geometry_ref="g1", distance=5, unit="miles",
                depends_on=["n1"],
            ),
            "n3": SpatialJoinNode(
                node_id="n3", output_artifact="sj1",
                layer_url="https://example.com/0", geometry_ref="b1",
                depends_on=["n2"],
            ),
        }
        graph = ExecutionGraph(nodes)
        levels = graph.topological_levels()
        assert levels == [["n1"], ["n2"], ["n3"]]

    def test_parallel_siblings(self):
        """n2 and n3 both depend on n1 — same level."""
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
            "n2": QueryNode(
                node_id="n2", output_artifact="f1",
                layer_url="https://example.com/0",
                depends_on=["n1"],
            ),
            "n3": QueryNode(
                node_id="n3", output_artifact="f2",
                layer_url="https://example.com/1",
                depends_on=["n1"],
            ),
        }
        graph = ExecutionGraph(nodes)
        levels = graph.topological_levels()
        assert levels == [["n1"], ["n2", "n3"]]

    def test_diamond_dependency(self):
        """n1 → (n2, n3) → n4."""
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
            "n2": BufferNode(
                node_id="n2", output_artifact="b1",
                geometry_ref="g1", distance=5, unit="miles",
                depends_on=["n1"],
            ),
            "n3": QueryNode(
                node_id="n3", output_artifact="f1",
                layer_url="https://example.com/0",
                depends_on=["n1"],
            ),
            "n4": SpatialJoinNode(
                node_id="n4", output_artifact="sj1",
                layer_url="https://example.com/1", geometry_ref="b1",
                depends_on=["n2", "n3"],
            ),
        }
        graph = ExecutionGraph(nodes)
        levels = graph.topological_levels()
        assert levels == [["n1"], ["n2", "n3"], ["n4"]]

    def test_single_node(self):
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
        }
        graph = ExecutionGraph(nodes)
        levels = graph.topological_levels()
        assert levels == [["n1"]]

    def test_two_independent_roots(self):
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
            "n2": GeocodeNode(node_id="n2", output_artifact="g2", address="B"),
        }
        graph = ExecutionGraph(nodes)
        levels = graph.topological_levels()
        assert levels == [["n1", "n2"]]


# ---------------------------------------------------------------------------
# Graph Validation Tests
# ---------------------------------------------------------------------------


class TestGraphValidation:
    def test_cycle_detected(self):
        """Direct cycle: n1→n2→n1."""
        with pytest.raises(GraphValidationError, match="cycle"):
            ExecutionGraph({
                "n1": GeocodeNode(
                    node_id="n1", output_artifact="g1", address="A",
                    depends_on=["n2"],
                ),
                "n2": GeocodeNode(
                    node_id="n2", output_artifact="g2", address="B",
                    depends_on=["n1"],
                ),
            })

    def test_missing_dependency(self):
        with pytest.raises(GraphValidationError, match="n99"):
            ExecutionGraph({
                "n1": GeocodeNode(
                    node_id="n1", output_artifact="g1", address="A",
                    depends_on=["n99"],
                ),
            })

    def test_empty_graph(self):
        with pytest.raises(GraphValidationError, match="no nodes"):
            ExecutionGraph({})

    def test_self_cycle(self):
        with pytest.raises(GraphValidationError, match="cycle"):
            ExecutionGraph({
                "n1": GeocodeNode(
                    node_id="n1", output_artifact="g1", address="A",
                    depends_on=["n1"],
                ),
            })


# ---------------------------------------------------------------------------
# Graph Execution Tests
# ---------------------------------------------------------------------------


class TestGraphExecution:
    @pytest.mark.asyncio
    async def test_sequential_execution(self):
        """Linear chain executes in order and stores artifacts."""
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
            "n2": BufferNode(
                node_id="n2", output_artifact="b1",
                geometry_ref="g1", distance=5, unit="miles",
                depends_on=["n1"],
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map=_make_executor_map())

        result = await runtime.execute(graph, ctx)

        assert "g1" in ctx.artifacts
        assert "b1" in ctx.artifacts
        assert len(result.node_timing) == 2
        assert result.errors == {}

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Parallel siblings produce a parallel group."""
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
            "n2": QueryNode(
                node_id="n2", output_artifact="f1",
                layer_url="https://example.com/0",
                depends_on=["n1"],
            ),
            "n3": QueryNode(
                node_id="n3", output_artifact="f2",
                layer_url="https://example.com/1",
                depends_on=["n1"],
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map=_make_executor_map())

        result = await runtime.execute(graph, ctx)

        assert ["n2", "n3"] in result.parallel_groups
        assert len(result.node_timing) == 3

    @pytest.mark.asyncio
    async def test_error_isolation(self):
        """Failed node doesn't lose previously completed artifacts."""

        async def fail_executor(node, ctx):
            raise RuntimeError("boom")

        executor_map = _make_executor_map()
        executor_map["buffer"] = fail_executor

        nodes = {
            "n1": GeocodeNode(
                node_id="n1", output_artifact="g1", address="A",
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n2": BufferNode(
                node_id="n2", output_artifact="b1",
                geometry_ref="g1", distance=5, unit="miles",
                depends_on=["n1"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map=executor_map)

        result = await runtime.execute(graph, ctx)

        assert "g1" in ctx.artifacts
        assert "n2" in result.errors
        assert "boom" in result.errors["n2"]

    @pytest.mark.asyncio
    async def test_dependent_skipped_on_upstream_failure(self):
        """When n2 fails, n3 (depends on n2) is skipped."""

        async def fail_executor(node, ctx):
            raise RuntimeError("fail")

        executor_map = _make_executor_map()
        executor_map["buffer"] = fail_executor

        nodes = {
            "n1": GeocodeNode(
                node_id="n1", output_artifact="g1", address="A",
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n2": BufferNode(
                node_id="n2", output_artifact="b1",
                geometry_ref="g1", distance=5, unit="miles",
                depends_on=["n1"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n3": SpatialJoinNode(
                node_id="n3", output_artifact="sj1",
                layer_url="https://example.com/0", geometry_ref="b1",
                depends_on=["n2"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map=executor_map)

        result = await runtime.execute(graph, ctx)

        assert "n2" in result.errors
        assert "n3" in result.skipped

    @pytest.mark.asyncio
    async def test_partial_results_on_failure(self):
        """Completed nodes produce artifacts even when later nodes fail."""

        call_order = []

        async def tracking_exec(node, ctx):
            call_order.append(node.node_id)
            ctx.put(
                node.output_artifact,
                f"data-{node.node_id}",
                ArtifactType.GEOMETRY,
                node.node_id,
            )

        async def fail_exec(node, ctx):
            call_order.append(node.node_id)
            raise RuntimeError("late failure")

        executor_map = _make_executor_map()
        executor_map["geocode"] = tracking_exec
        executor_map["query"] = fail_exec

        nodes = {
            "n1": GeocodeNode(
                node_id="n1", output_artifact="g1", address="A",
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n2": QueryNode(
                node_id="n2", output_artifact="f1",
                layer_url="https://example.com/0",
                depends_on=["n1"],
                retry_policy=RetryPolicy(max_attempts=1),
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map=executor_map)

        result = await runtime.execute(graph, ctx)

        assert "g1" in result.artifacts_produced
        assert "n2" in result.errors

    @pytest.mark.asyncio
    async def test_retry_interaction(self):
        """Node retries on transient error, succeeds on second attempt."""
        attempts = []

        async def flaky_executor(node, ctx):
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutError("transient")
            ctx.put(
                node.output_artifact, "ok",
                ArtifactType.GEOMETRY, node.node_id,
            )

        executor_map = _make_executor_map()
        executor_map["geocode"] = flaky_executor

        nodes = {
            "n1": GeocodeNode(
                node_id="n1", output_artifact="g1", address="A",
                retry_policy=RetryPolicy(
                    max_attempts=2, base_delay=0.01, jitter=False,
                ),
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map=executor_map)

        result = await runtime.execute(graph, ctx)

        assert result.errors == {}
        assert ctx.get("g1") == "ok"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_missing_executor_type(self):
        """Unknown node type produces an error, not a crash."""
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map={})  # empty map

        result = await runtime.execute(graph, ctx)

        assert "n1" in result.errors
        assert "No executor" in result.errors["n1"]


# ---------------------------------------------------------------------------
# Progress Event Emission Tests
# ---------------------------------------------------------------------------


class TestProgressEvents:
    @pytest.mark.asyncio
    async def test_node_start_and_complete_events(self):
        events = []

        def callback(event):
            events.append(event)

        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx(progress_callback=callback)
        runtime = GraphRuntime(executor_map=_make_executor_map())

        await runtime.execute(graph, ctx)

        types = [e["type"] for e in events]
        assert "node_start" in types
        assert "node_complete" in types
        assert "graph_complete" in types

    @pytest.mark.asyncio
    async def test_node_start_event_fields(self):
        events = []

        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx(progress_callback=lambda e: events.append(e))
        runtime = GraphRuntime(executor_map=_make_executor_map())

        await runtime.execute(graph, ctx)

        start = next(e for e in events if e["type"] == "node_start")
        assert start["node_id"] == "n1"
        assert start["node_type"] == "geocode"

    @pytest.mark.asyncio
    async def test_node_complete_has_ms(self):
        events = []

        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx(progress_callback=lambda e: events.append(e))
        runtime = GraphRuntime(executor_map=_make_executor_map())

        await runtime.execute(graph, ctx)

        complete = next(e for e in events if e["type"] == "node_complete")
        assert "ms" in complete
        assert complete["ms"] >= 0

    @pytest.mark.asyncio
    async def test_graph_complete_event(self):
        events = []

        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
            "n2": QueryNode(
                node_id="n2", output_artifact="f1",
                layer_url="https://example.com/0",
                depends_on=["n1"],
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx(progress_callback=lambda e: events.append(e))
        runtime = GraphRuntime(executor_map=_make_executor_map())

        await runtime.execute(graph, ctx)

        gc = next(e for e in events if e["type"] == "graph_complete")
        assert gc["nodes_executed"] == 2
        assert gc["total_ms"] >= 0

    @pytest.mark.asyncio
    async def test_node_retry_event(self):
        events = []
        attempts = []

        async def flaky(node, ctx):
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutError("timeout")
            ctx.put(
                node.output_artifact, "ok",
                ArtifactType.GEOMETRY, node.node_id,
            )

        executor_map = _make_executor_map()
        executor_map["geocode"] = flaky

        nodes = {
            "n1": GeocodeNode(
                node_id="n1", output_artifact="g1", address="A",
                retry_policy=RetryPolicy(
                    max_attempts=2, base_delay=0.01, jitter=False,
                ),
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx(progress_callback=lambda e: events.append(e))
        runtime = GraphRuntime(executor_map=executor_map)

        await runtime.execute(graph, ctx)

        retry_events = [e for e in events if e["type"] == "node_retry"]
        assert len(retry_events) >= 1
        assert retry_events[0]["node_id"] == "n1"

    @pytest.mark.asyncio
    async def test_no_callback_no_crash(self):
        """Graph executes fine without progress callback."""
        nodes = {
            "n1": GeocodeNode(node_id="n1", output_artifact="g1", address="A"),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx()
        runtime = GraphRuntime(executor_map=_make_executor_map())

        result = await runtime.execute(graph, ctx)
        assert result.errors == {}

    @pytest.mark.asyncio
    async def test_skipped_event_emitted(self):
        events = []

        async def fail(node, ctx):
            raise RuntimeError("fail")

        executor_map = _make_executor_map()
        executor_map["geocode"] = fail

        nodes = {
            "n1": GeocodeNode(
                node_id="n1", output_artifact="g1", address="A",
                retry_policy=RetryPolicy(max_attempts=1),
            ),
            "n2": QueryNode(
                node_id="n2", output_artifact="f1",
                layer_url="https://example.com/0",
                depends_on=["n1"],
            ),
        }
        graph = ExecutionGraph(nodes)
        ctx = _make_ctx(progress_callback=lambda e: events.append(e))
        runtime = GraphRuntime(executor_map=executor_map)

        result = await runtime.execute(graph, ctx)

        skipped = [e for e in events if e["type"] == "node_skipped"]
        assert len(skipped) == 1
        assert skipped[0]["node_id"] == "n2"
