"""Flat DAG intent models for LLM-produced query plans.

These models represent the LLM output format (flat node arrays with
explicit ``depend_on`` edges) matching ``input_query_sample2.json``.
The expander converts these into typed ``ExecutionGraph`` nodes.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Node dependency
# ---------------------------------------------------------------------------


class NodeDependency(BaseModel):
    """Explicit dependency edge between flat plan nodes."""

    node_id: str
    join_type: Optional[str] = None  # "spatial_join"


# ---------------------------------------------------------------------------
# Flat plan node
# ---------------------------------------------------------------------------


class FlatPlanNode(BaseModel):
    """A single node in the flat DAG plan.

    Covers all node types: ``where``, ``count``, ``address``,
    ``location``, ``tool`` (buffer/proximity).
    """

    node_id: str
    intent: str = ""
    depend_on: List[NodeDependency] = Field(default_factory=list)
    type: str  # "where" | "count" | "address" | "location" | "tool"
    layer: Optional[str] = None
    where: Optional[str] = None
    out_fields: Optional[List[str]] = None
    join_type: Optional[str] = None  # "spatial_join" | "buffer" | "proximity"
    distance: Optional[float] = None
    unit: Optional[str] = None
    top: Optional[int] = None
    address: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    alias: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level intent
# ---------------------------------------------------------------------------


class FlatPlanIntent(BaseModel):
    """Top-level LLM-produced intent with flat node arrays.

    Only one of ``query``, ``locate``, or ``analyze`` will be populated
    based on the ``action`` field.
    """

    action: str  # "query" | "locate" | "analyze" | "message"
    message: Optional[str] = None
    query: Optional[List[FlatPlanNode]] = None
    locate: Optional[List[FlatPlanNode]] = None
    analyze: Optional[List[FlatPlanNode]] = None
