"""Typed spatial execution node models.

Provides a discriminated union (``TypedNode``) of all spatial node types
that the graph runtime can execute.  Each node carries its own input
parameters, output artifact key, dependency edges, and optional retry
policy.
"""

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from .resilience import RetryPolicy


# ---------------------------------------------------------------------------
# BaseNode
# ---------------------------------------------------------------------------


class BaseNode(BaseModel):
    """Common fields shared by all graph node types.

    Args:
        node_id: Unique identifier within the graph (e.g. ``"n1"``).
        node_type: Discriminator field — set by each concrete subclass.
        output_artifact: Key under which the node stores its result in
            ``GraphContext.artifacts``.
        depends_on: List of ``node_id`` values that must complete before
            this node executes.
        retry_policy: Optional per-node retry configuration.  Falls back
            to the runtime default when ``None``.
    """

    node_id: str
    node_type: str
    output_artifact: str
    depends_on: List[str] = Field(default_factory=list)
    retry_policy: Optional[RetryPolicy] = None

    model_config = {"frozen": False}


# ---------------------------------------------------------------------------
# Concrete Node Types
# ---------------------------------------------------------------------------


class GeocodeNode(BaseNode):
    """Convert an address / place name to a geometry artifact."""

    node_type: Literal["geocode"] = "geocode"
    address: str


class QueryNode(BaseNode):
    """Query features from an ArcGIS layer with optional spatial filter."""

    node_type: Literal["query"] = "query"
    layer_url: str
    where: Optional[str] = None
    geometry_ref: Optional[str] = None
    out_fields: Optional[List[str]] = None


class BufferNode(BaseNode):
    """Create a buffer geometry around an input geometry artifact."""

    node_type: Literal["buffer"] = "buffer"
    geometry_ref: str
    distance: float = Field(gt=0)
    unit: str


class UnionNode(BaseNode):
    """Union geometries from a feature set into a single geometry."""

    node_type: Literal["union"] = "union"
    features_ref: str


class SpatialJoinNode(BaseNode):
    """Query features from a layer using a geometry as spatial filter."""

    node_type: Literal["spatial_join"] = "spatial_join"
    layer_url: str
    geometry_ref: str
    spatial_rel: str = "esriSpatialRelIntersects"
    where: Optional[str] = None
    out_fields: Optional[List[str]] = None


class ProximityNode(BaseNode):
    """Find features near a geometry within a specified distance."""

    node_type: Literal["proximity"] = "proximity"
    geometry_ref: str
    layer_url: str
    distance: float = Field(gt=0)
    unit: str
    top: int = 2000
    where: Optional[str] = None
    out_fields: Optional[List[str]] = None


class SummarizeNode(BaseNode):
    """Compute field statistics on a feature set artifact."""

    node_type: Literal["summarize"] = "summarize"
    features_ref: str
    field_name: str
    stat_type: str


class CountNode(BaseNode):
    """Count features matching criteria."""

    node_type: Literal["count"] = "count"
    layer_url: str
    geometry_ref: Optional[str] = None
    where: Optional[str] = None


# ---------------------------------------------------------------------------
# Discriminated Union
# ---------------------------------------------------------------------------

TypedNode = Annotated[
    Union[
        GeocodeNode,
        QueryNode,
        BufferNode,
        UnionNode,
        SpatialJoinNode,
        ProximityNode,
        SummarizeNode,
        CountNode,
    ],
    Field(discriminator="node_type"),
]
