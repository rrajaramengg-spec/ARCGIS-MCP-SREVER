"""DAG-based execution engine for spatial operation pipelines.

Provides ``ExecutionGraph`` (validated DAG structure), ``GraphResult``
(execution outcome), and ``GraphRuntime`` (the engine that executes
nodes in topological order with bounded parallelism).
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from .context import ArtifactNotFoundError, GraphContext, NodeTiming
from .nodes import TypedNode
from .resilience import RetryPolicy, retry_with_backoff

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GraphValidationError(Exception):
    """Raised when the execution graph has structural errors."""


class NodeExecutionError(Exception):
    """Raised when a node executor fails after retries."""

    def __init__(self, node_id: str, message: str) -> None:
        self.node_id = node_id
        super().__init__(f"Node '{node_id}': {message}")


# ---------------------------------------------------------------------------
# GraphResult
# ---------------------------------------------------------------------------


@dataclass
class GraphResult:
    """Outcome of a complete graph execution.

    Args:
        node_timing: Per-node timing records.
        artifacts_produced: Keys of artifacts stored during execution.
        parallel_groups: Groups of node IDs that executed concurrently.
        retry_budget_used: Total retries consumed across all nodes.
        errors: Mapping of failed ``node_id`` → error message.
        data: Final output data (last leaf node's artifact or merged).
        skipped: Node IDs skipped due to upstream failures.
    """

    node_timing: List[NodeTiming] = field(default_factory=list)
    artifacts_produced: List[str] = field(default_factory=list)
    parallel_groups: List[List[str]] = field(default_factory=list)
    retry_budget_used: int = 0
    errors: Dict[str, str] = field(default_factory=dict)
    data: Any = None
    skipped: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ExecutionGraph
# ---------------------------------------------------------------------------


class ExecutionGraph:
    """Validated DAG of typed spatial nodes.

    Args:
        nodes: Mapping of ``node_id`` → typed node instance.
        output_mode: How the final result should be presented
            (e.g. ``["map_layer"]``).
    """

    def __init__(
        self,
        nodes: Dict[str, TypedNode],
        output_mode: Optional[List[str]] = None,
    ) -> None:
        self.nodes = nodes
        self.output_mode = output_mode or []
        self.validate()

    # -- Validation ---------------------------------------------------------

    def validate(self) -> None:
        """Check structural correctness: non-empty, no missing deps, no cycles."""
        if not self.nodes:
            raise GraphValidationError("ExecutionGraph has no nodes")

        node_ids = set(self.nodes.keys())

        # Missing dependency references.
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in node_ids:
                    raise GraphValidationError(
                        f"Node '{nid}' depends on '{dep}' which does not exist"
                    )

        # Cycle detection via Kahn's algorithm.
        in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                in_degree[nid] += 1  # nid depends on dep (not counted above)

        # Recount properly: in_degree[nid] = number of deps nid has.
        in_degree = {nid: len(self.nodes[nid].depends_on) for nid in node_ids}
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited = 0

        temp_in_degree = dict(in_degree)
        while queue:
            current = queue.popleft()
            visited += 1
            # Find all nodes that depend on current.
            for nid, node in self.nodes.items():
                if current in node.depends_on:
                    temp_in_degree[nid] -= 1
                    if temp_in_degree[nid] == 0:
                        queue.append(nid)

        if visited != len(node_ids):
            raise GraphValidationError(
                "ExecutionGraph contains a dependency cycle"
            )

    # -- Topological sort with level grouping -------------------------------

    def topological_levels(self) -> List[List[str]]:
        """Return nodes grouped by topological level.

        Nodes in the same level have no dependencies on each other and
        can execute concurrently.

        Returns:
            List of levels, each containing a list of ``node_id`` strings.
        """
        in_degree = {nid: len(self.nodes[nid].depends_on) for nid in self.nodes}
        current_level = [nid for nid, deg in in_degree.items() if deg == 0]
        levels: List[List[str]] = []

        while current_level:
            levels.append(sorted(current_level))  # sorted for determinism
            next_level: List[str] = []
            for nid in current_level:
                for other_id, other_node in self.nodes.items():
                    if nid in other_node.depends_on:
                        in_degree[other_id] -= 1
                        if in_degree[other_id] == 0:
                            next_level.append(other_id)
            current_level = next_level

        return levels


# ---------------------------------------------------------------------------
# Default retry policy
# ---------------------------------------------------------------------------

_DEFAULT_RETRY = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=8.0)


# ---------------------------------------------------------------------------
# GraphRuntime
# ---------------------------------------------------------------------------


class GraphRuntime:
    """Executes an ``ExecutionGraph`` using topological traversal with
    bounded parallel execution, per-node retry, and progress emission.

    Args:
        executor_map: Mapping of ``node_type`` → async executor function.
            Each function has the signature
            ``(node: TypedNode, ctx: GraphContext) -> Any``.
    """

    def __init__(
        self,
        executor_map: Dict[str, Callable],
    ) -> None:
        self._executor_map = executor_map

    async def execute(
        self,
        graph: ExecutionGraph,
        ctx: GraphContext,
    ) -> GraphResult:
        """Execute the graph in dependency order.

        Args:
            graph: Validated execution graph.
            ctx: Request-scoped context with artifact store and MCP client.

        Returns:
            ``GraphResult`` with timing, artifacts, errors, and final data.
        """
        graph_start = time.monotonic()
        result = GraphResult()
        failed_nodes: Set[str] = set()
        skipped_nodes: Set[str] = set()

        levels = graph.topological_levels()

        for level in levels:
            # Record parallel groups with >1 node.
            if len(level) > 1:
                result.parallel_groups.append(list(level))

            # Determine which nodes in this level can run.
            runnable: List[str] = []
            for nid in level:
                upstream_failed = any(
                    dep in failed_nodes or dep in skipped_nodes
                    for dep in graph.nodes[nid].depends_on
                )
                if upstream_failed:
                    skipped_nodes.add(nid)
                    result.skipped.append(nid)
                    logger.warning("Skipping node %s — upstream failure", nid)
                    self._emit(ctx, {
                        "type": "node_skipped",
                        "node_id": nid,
                        "node_type": graph.nodes[nid].node_type,
                    })
                else:
                    runnable.append(nid)

            if not runnable:
                continue

            # Execute runnable nodes in parallel.
            tasks = [
                self._execute_node(graph.nodes[nid], ctx, result, failed_nodes)
                for nid in runnable
            ]
            await asyncio.gather(*tasks)

        # Final result assembly.
        result.artifacts_produced = list(ctx.artifacts.keys())
        result.retry_budget_used = ctx.retry_budget.used
        result.node_timing = list(ctx.node_timing)

        # Set data to the last leaf node's artifact if available.
        leaf_nodes = [
            nid for nid in graph.nodes
            if nid not in failed_nodes and nid not in skipped_nodes
        ]
        if leaf_nodes:
            last_leaf = leaf_nodes[-1]
            artifact_key = graph.nodes[last_leaf].output_artifact
            if artifact_key in ctx.artifacts:
                result.data = ctx.artifacts[artifact_key]

        total_ms = (time.monotonic() - graph_start) * 1000
        self._emit(ctx, {
            "type": "graph_complete",
            "nodes_executed": len(ctx.node_timing),
            "total_ms": round(total_ms, 2),
        })

        return result

    async def _execute_node(
        self,
        node: TypedNode,
        ctx: GraphContext,
        result: GraphResult,
        failed_nodes: Set[str],
    ) -> None:
        """Execute a single node with retry, timing, and error isolation."""
        executor = self._executor_map.get(node.node_type)
        if executor is None:
            error_msg = f"No executor for node type '{node.node_type}'"
            result.errors[node.node_id] = error_msg
            failed_nodes.add(node.node_id)
            logger.error("Node %s — %s", node.node_id, error_msg)
            return

        policy = node.retry_policy or _DEFAULT_RETRY
        retries = 0
        node_start = time.monotonic()

        self._emit(ctx, {
            "type": "node_start",
            "node_id": node.node_id,
            "node_type": node.node_type,
        })

        try:
            async def _run() -> Any:
                if ctx.circuit_breaker is not None:
                    return await ctx.circuit_breaker.call(
                        lambda: executor(node, ctx)
                    )
                return await executor(node, ctx)

            # Wrap in retry_with_backoff, tracking retries via a counter.
            attempt_count = 0

            async def _run_with_tracking() -> Any:
                nonlocal attempt_count, retries
                attempt_count += 1
                if attempt_count > 1:
                    retries += 1
                    self._emit(ctx, {
                        "type": "node_retry",
                        "node_id": node.node_id,
                        "attempt": attempt_count,
                        "error": str(last_error),
                    })
                if ctx.circuit_breaker is not None:
                    return await ctx.circuit_breaker.call(
                        lambda: executor(node, ctx)
                    )
                return await executor(node, ctx)

            last_error: Optional[Exception] = None

            async def _run_tracked() -> Any:
                nonlocal last_error
                try:
                    return await _run_with_tracking()
                except Exception as exc:
                    last_error = exc
                    raise

            await retry_with_backoff(_run_tracked, policy, ctx.retry_budget)

        except Exception as exc:
            elapsed_ms = (time.monotonic() - node_start) * 1000
            result.errors[node.node_id] = str(exc)
            failed_nodes.add(node.node_id)
            ctx.node_timing.append(NodeTiming(
                node_id=node.node_id,
                node_type=node.node_type,
                ms=round(elapsed_ms, 2),
                retries=retries,
                status="error",
            ))
            logger.error(
                "Node %s failed after %d retries — %s",
                node.node_id, retries, exc,
            )
            return

        elapsed_ms = (time.monotonic() - node_start) * 1000
        ctx.node_timing.append(NodeTiming(
            node_id=node.node_id,
            node_type=node.node_type,
            ms=round(elapsed_ms, 2),
            retries=retries,
            status="success",
        ))
        self._emit(ctx, {
            "type": "node_complete",
            "node_id": node.node_id,
            "node_type": node.node_type,
            "ms": round(elapsed_ms, 2),
        })

    @staticmethod
    def _emit(ctx: GraphContext, event: Dict[str, Any]) -> None:
        """Emit a progress event if callback is set."""
        if ctx.progress_callback is not None:
            try:
                ctx.progress_callback(event)
            except Exception:
                logger.debug("Progress callback error", exc_info=True)
