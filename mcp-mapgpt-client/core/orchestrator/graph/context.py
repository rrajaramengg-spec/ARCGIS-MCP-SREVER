"""Request-scoped execution context for graph runtime.

Provides the ``GraphContext`` dataclass that carries all per-request state
through node executors without relying on ContextVars (which do not
propagate writes through ``asyncio.gather`` child tasks).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.contracts import IMCPClient

from .resilience import CircuitBreaker, RetryBudget

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ArtifactType
# ---------------------------------------------------------------------------


class ArtifactType(str, Enum):
    """Classification of artifacts produced by graph nodes."""

    GEOMETRY = "GEOMETRY"
    FEATURE_SET = "FEATURE_SET"
    BUFFER_ZONE = "BUFFER_ZONE"
    COUNT = "COUNT"
    SUMMARY = "SUMMARY"
    UNION_GEOMETRY = "UNION_GEOMETRY"


# ---------------------------------------------------------------------------
# ArtifactMeta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactMeta:
    """Lineage metadata for a stored artifact.

    Args:
        producer_node_id: The ``node_id`` of the node that created this
            artifact.
        artifact_type: Semantic type of the artifact value.
        created_at: Monotonic timestamp when the artifact was stored.
    """

    producer_node_id: str
    artifact_type: ArtifactType
    created_at: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# NodeTiming
# ---------------------------------------------------------------------------


@dataclass
class NodeTiming:
    """Execution timing record for a single graph node.

    Args:
        node_id: Unique identifier of the executed node.
        node_type: Discriminator type of the node (e.g. ``"geocode"``).
        ms: Wall-clock execution time in milliseconds.
        retries: Number of retries consumed by this node.
        status: Final execution status (``"success"`` or ``"error"``).
    """

    node_id: str
    node_type: str
    ms: float = 0.0
    retries: int = 0
    status: str = "success"


# ---------------------------------------------------------------------------
# GraphContext
# ---------------------------------------------------------------------------


class ArtifactNotFoundError(KeyError):
    """Raised when a requested artifact does not exist in the store."""


@dataclass
class GraphContext:
    """Request-scoped state carried through all graph node executors.

    This is an explicit dataclass — **not** ContextVars — because parallel
    nodes running under ``asyncio.gather`` must share and mutate the same
    artifact store.  ContextVar writes in child tasks are invisible to the
    parent.

    Args:
        correlation_id: Request correlation ID for structured logging.
        mcp_client: MCP client for node executors to call tools.
        retry_budget: Graph-level retry budget shared across all nodes.
        progress_callback: Optional callback for per-node progress events.
        semaphore: Optional shared semaphore for ArcGIS concurrency.
    """

    correlation_id: str
    mcp_client: IMCPClient
    retry_budget: RetryBudget = field(default_factory=RetryBudget)
    progress_callback: Optional[Callable] = None
    semaphore: Optional[asyncio.Semaphore] = None
    circuit_breaker: Optional[CircuitBreaker] = None

    # Internal stores — initialised empty, populated during execution.
    artifacts: Dict[str, Any] = field(default_factory=dict)
    artifact_meta: Dict[str, ArtifactMeta] = field(default_factory=dict)
    node_timing: List[NodeTiming] = field(default_factory=list)

    # -- Artifact helpers ---------------------------------------------------

    def put(
        self,
        key: str,
        value: Any,
        artifact_type: ArtifactType,
        producer_node_id: str,
    ) -> None:
        """Store an artifact with lineage metadata.

        Args:
            key: Artifact reference key (e.g. ``"geom_1"``).
            value: The artifact value.
            artifact_type: Semantic type classification.
            producer_node_id: ``node_id`` of the producing node.
        """
        self.artifacts[key] = value
        self.artifact_meta[key] = ArtifactMeta(
            producer_node_id=producer_node_id,
            artifact_type=artifact_type,
        )
        logger.debug(
            "Artifact stored — key=%s type=%s producer=%s",
            key,
            artifact_type.value,
            producer_node_id,
        )

    def get(self, key: str) -> Any:
        """Retrieve an artifact by key.

        Args:
            key: Artifact reference key.

        Returns:
            The stored artifact value.

        Raises:
            ArtifactNotFoundError: If *key* does not exist.
        """
        try:
            return self.artifacts[key]
        except KeyError:
            raise ArtifactNotFoundError(
                f"Artifact '{key}' not found. "
                f"Available: {list(self.artifacts.keys())}"
            )
