"""Graph-based execution engine for spatial operation pipelines."""

from .context import (
    ArtifactMeta,
    ArtifactNotFoundError,
    ArtifactType,
    GraphContext,
    NodeTiming,
)
from .nodes import (
    BaseNode,
    BufferNode,
    CountNode,
    GeocodeNode,
    ProximityNode,
    QueryNode,
    SpatialJoinNode,
    SummarizeNode,
    TypedNode,
    UnionNode,
)
from .resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryBudget,
    RetryBudgetExhaustedError,
    RetryPolicy,
    retry_with_backoff,
)
from .executors import EXECUTOR_MAP
from core.tool_names import ARCGIS_TOOL_NAMES
from .results import (
    BufferResult,
    CountResult,
    FeatureSetResult,
    GeocodeResult,
    SummaryResult,
)
from .expander import PlanExpansionError, expand_plan
from .geometry_utils import union_feature_geometries
from .intent import FlatPlanIntent, FlatPlanNode, NodeDependency
from .runtime import (
    ExecutionGraph,
    GraphResult,
    GraphRuntime,
    GraphValidationError,
    NodeExecutionError,
)

__all__ = [
    # context
    "ArtifactMeta",
    "ArtifactNotFoundError",
    "ArtifactType",
    "GraphContext",
    "NodeTiming",
    # nodes
    "BaseNode",
    "BufferNode",
    "CountNode",
    "GeocodeNode",
    "ProximityNode",
    "QueryNode",
    "SpatialJoinNode",
    "SummarizeNode",
    "TypedNode",
    "UnionNode",
    # resilience
    "CircuitBreaker",
    "CircuitOpenError",
    "RetryBudget",
    "RetryBudgetExhaustedError",
    "RetryPolicy",
    "retry_with_backoff",
    # runtime
    "ExecutionGraph",
    "GraphResult",
    "GraphRuntime",
    "GraphValidationError",
    "NodeExecutionError",
    # executors
    "EXECUTOR_MAP",
    # expander
    "PlanExpansionError",
    "expand_plan",
    # intent
    "FlatPlanIntent",
    "FlatPlanNode",
    "NodeDependency",
    # geometry_utils
    "union_feature_geometries",
]
