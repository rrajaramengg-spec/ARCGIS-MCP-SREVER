"""Plan expansion — convert flat LLM intent into an ExecutionGraph.

The LLM produces flat node arrays with explicit ``depend_on`` edges
.  This module deterministically
expands them into typed node graphs with auto-injected plumbing nodes
(UnionNode, BufferNode, GeocodeNode).  No LLM calls occur during expansion.
"""

import logging
from typing import Any, Dict, List, Optional

from .intent import FlatPlanIntent, FlatPlanNode
from .nodes import (
    BufferNode,
    CountNode,
    GeocodeNode,
    ProximityNode,
    QueryNode,
    SpatialJoinNode,
    TypedNode,
    UnionNode,
)
from .resilience import RetryPolicy
from .runtime import ExecutionGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PlanExpansionError(Exception):
    """Raised when a plan cannot be expanded into a valid graph."""


# ---------------------------------------------------------------------------
# Default retry policies per node type
# ---------------------------------------------------------------------------

_DEFAULT_RETRY = RetryPolicy(max_attempts=3, base_delay=0.5, max_delay=5.0, jitter=True)
_NO_RETRY = RetryPolicy(max_attempts=1)

_RETRY_BY_TYPE = {
    "geocode": _DEFAULT_RETRY,
    "query": _DEFAULT_RETRY,
    "buffer": _DEFAULT_RETRY,
    "spatial_join": _DEFAULT_RETRY,
    "proximity": _DEFAULT_RETRY,
    "union": _NO_RETRY,
    "summarize": _NO_RETRY,
    "count": _DEFAULT_RETRY,
}


# ---------------------------------------------------------------------------
# Layer URL lookup
# ---------------------------------------------------------------------------


def _build_layer_lookup(rag_layers: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build a case-insensitive layer name → URL mapping."""
    lookup: Dict[str, str] = {}
    for layer in rag_layers:
        name = (layer.get("layer_name") or layer.get("name") or "").strip().upper()
        url = layer.get("url", "")
        if name and url:
            lookup[name] = url
    return lookup


def _resolve_layer_url(layer: Optional[str], lookup: Dict[str, str]) -> str:
    """Resolve a layer URL from layer name via RAG lookup."""
    if not layer:
        return ""
    # If the LLM already provided a full URL, use it directly
    if layer.startswith("http://") or layer.startswith("https://"):
        return layer
    url = lookup.get(layer.strip().upper(), "")
    if url:
        return url
    return ""


# ---------------------------------------------------------------------------
# Expansion entry point
# ---------------------------------------------------------------------------


def expand_plan(
    plan: Dict[str, Any],
    rag_layers: Optional[List[Dict[str, Any]]] = None,
) -> ExecutionGraph:
    """Expand a flat LLM plan dict into an ExecutionGraph.

    Args:
        plan: Raw LLM plan dict with ``action``, and one of
            ``query``/``locate``/``analyze`` keys containing flat node arrays.
        rag_layers: Optional RAG layer metadata (for URL resolution).

    Returns:
        Validated ``ExecutionGraph`` ready for execution.

    Raises:
        PlanExpansionError: If the plan is malformed or unsupported.
    """
    try:
        intent = FlatPlanIntent.model_validate(plan)
    except Exception as exc:
        raise PlanExpansionError(f"Invalid plan schema: {exc}") from exc

    layer_lookup = _build_layer_lookup(rag_layers or [])

    # Route to the correct node list based on action.
    flat_nodes: List[FlatPlanNode] = []
    if intent.action == "query" and intent.query:
        flat_nodes = intent.query
    elif intent.action == "locate" and intent.locate:
        flat_nodes = intent.locate
    elif intent.action == "analyze" and intent.analyze:
        flat_nodes = intent.analyze
    elif intent.action == "message":
        raise PlanExpansionError("Message actions are not executable")
    else:
        raise PlanExpansionError(
            f"Unsupported or empty action: '{intent.action}'"
        )

    if not flat_nodes:
        raise PlanExpansionError("Plan expansion produced zero nodes")

    nodes = _expand_flat_nodes(flat_nodes, layer_lookup)

    if not nodes:
        raise PlanExpansionError("Plan expansion produced zero typed nodes")

    return ExecutionGraph(nodes)


# ---------------------------------------------------------------------------
# Flat node expansion
# ---------------------------------------------------------------------------


def _expand_flat_nodes(
    flat_nodes: List[FlatPlanNode],
    layer_lookup: Dict[str, str],
) -> Dict[str, TypedNode]:
    """Convert flat plan nodes into typed graph nodes.

    Auto-injects UnionNode when a QueryNode has spatial-join dependents.
    Proximity nodes are mapped directly (2-node format: anchor → proximity
    with layer/where/out_fields inline on the tool node).
    """
    typed_nodes: Dict[str, TypedNode] = {}
    # Track which flat node_ids produce query results (candidates for union injection).
    query_node_artifacts: Dict[str, str] = {}
    # Track injected union nodes: parent_node_id → union_artifact.
    union_artifacts: Dict[str, str] = {}

    # First pass: create typed nodes.
    for flat in flat_nodes:
        _create_typed_node(flat, layer_lookup, typed_nodes, query_node_artifacts)

    # Second pass: inject UnionNode where needed (query parent with spatial-join children).
    for flat in flat_nodes:
        for dep in flat.depend_on:
            if dep.join_type == "spatial_join" and dep.node_id in query_node_artifacts:
                parent_id = dep.node_id
                if parent_id not in union_artifacts:
                    # Inject UnionNode between parent query and this node.
                    union_id = f"_union_{parent_id}"
                    union_artifact = f"union_{union_id}"
                    typed_nodes[union_id] = UnionNode(
                        node_id=union_id,
                        output_artifact=union_artifact,
                        features_ref=query_node_artifacts[parent_id],
                        depends_on=[parent_id],
                        retry_policy=_RETRY_BY_TYPE["union"],
                    )
                    union_artifacts[parent_id] = union_artifact

    # Third pass: fix geometry_ref and depends_on for spatial-join nodes.
    for flat in flat_nodes:
        nid = flat.node_id
        if nid not in typed_nodes:
            continue
        node = typed_nodes[nid]
        for dep in flat.depend_on:
            if dep.join_type == "spatial_join" and dep.node_id in union_artifacts:
                union_id = f"_union_{dep.node_id}"
                union_artifact = union_artifacts[dep.node_id]
                # Update geometry_ref and depends_on to point at union node.
                if hasattr(node, "geometry_ref"):
                    node.geometry_ref = union_artifact
                # Replace the parent dep with the union dep.
                if dep.node_id in node.depends_on:
                    node.depends_on.remove(dep.node_id)
                if union_id not in node.depends_on:
                    node.depends_on.append(union_id)

    return typed_nodes


def _create_typed_node(
    flat: FlatPlanNode,
    layer_lookup: Dict[str, str],
    typed_nodes: Dict[str, TypedNode],
    query_node_artifacts: Dict[str, str],
) -> None:
    """Create a single typed node from a flat plan node."""
    nid = flat.node_id
    artifact = f"artifact_{nid}"

    # Determine if this node has a spatial-join dependency.
    has_spatial_dep = any(d.join_type == "spatial_join" for d in flat.depend_on)
    dep_ids = [d.node_id for d in flat.depend_on]
    # Geometry ref: artifact of the dependency (will be fixed to union in second pass).
    geom_ref = f"artifact_{flat.depend_on[0].node_id}" if flat.depend_on else None

    if flat.type == "address":
        if not flat.address:
            raise PlanExpansionError(f"Node '{nid}' type='address' missing address")
        typed_nodes[nid] = GeocodeNode(
            node_id=nid,
            output_artifact=artifact,
            address=flat.address,
            depends_on=dep_ids,
            retry_policy=_RETRY_BY_TYPE["geocode"],
        )

    elif flat.type == "location":
        if flat.lon is None or flat.lat is None:
            raise PlanExpansionError(f"Node '{nid}' type='location' missing lon/lat")
        typed_nodes[nid] = GeocodeNode(
            node_id=nid,
            output_artifact=artifact,
            address=f"{flat.lon},{flat.lat}",
            depends_on=dep_ids,
            retry_policy=_RETRY_BY_TYPE["geocode"],
        )

    elif flat.type == "tool":
        if flat.join_type == "buffer":
            if not geom_ref:
                raise PlanExpansionError(f"Node '{nid}' type='tool' buffer missing dependency")
            typed_nodes[nid] = BufferNode(
                node_id=nid,
                output_artifact=artifact,
                geometry_ref=geom_ref,
                distance=flat.distance or 0,
                unit=flat.unit or "meters",
                depends_on=dep_ids,
                retry_policy=_RETRY_BY_TYPE["buffer"],
            )
        elif flat.join_type == "proximity":
            if not flat.layer:
                raise PlanExpansionError(
                    f"Node '{nid}' type='tool' proximity missing 'layer' field"
                )
            url = _resolve_layer_url(flat.layer, layer_lookup)
            if not geom_ref:
                raise PlanExpansionError(f"Node '{nid}' type='tool' proximity missing dependency")
            typed_nodes[nid] = ProximityNode(
                node_id=nid,
                output_artifact=artifact,
                geometry_ref=geom_ref,
                layer_url=url,
                distance=flat.distance or 0,
                unit=flat.unit or "meters",
                top=flat.top or 2000,
                where=flat.where,
                out_fields=flat.out_fields,
                depends_on=dep_ids,
                retry_policy=_RETRY_BY_TYPE["proximity"],
            )
        else:
            raise PlanExpansionError(f"Node '{nid}' unknown tool join_type: '{flat.join_type}'")

    elif flat.type == "count":
        url = _resolve_layer_url(flat.layer, layer_lookup)
        if has_spatial_dep and geom_ref:
            typed_nodes[nid] = CountNode(
                node_id=nid,
                output_artifact=artifact,
                layer_url=url,
                where=flat.where or "1=1",
                geometry_ref=geom_ref,
                depends_on=dep_ids,
                retry_policy=_RETRY_BY_TYPE["count"],
            )
        else:
            typed_nodes[nid] = CountNode(
                node_id=nid,
                output_artifact=artifact,
                layer_url=url,
                where=flat.where or "1=1",
                depends_on=dep_ids,
                retry_policy=_RETRY_BY_TYPE["count"],
            )

    elif flat.type == "where":
        url = _resolve_layer_url(flat.layer, layer_lookup)
        if has_spatial_dep and geom_ref:
            typed_nodes[nid] = SpatialJoinNode(
                node_id=nid,
                output_artifact=artifact,
                layer_url=url,
                geometry_ref=geom_ref,
                where=flat.where or "1=1",
                out_fields=flat.out_fields,
                depends_on=dep_ids,
                retry_policy=_RETRY_BY_TYPE["spatial_join"],
            )
        else:
            typed_nodes[nid] = QueryNode(
                node_id=nid,
                output_artifact=artifact,
                layer_url=url,
                where=flat.where or "1=1",
                out_fields=flat.out_fields,
                depends_on=dep_ids,
                retry_policy=_RETRY_BY_TYPE["query"],
            )
            # Track as query node for potential union injection.
            query_node_artifacts[nid] = artifact

    else:
        raise PlanExpansionError(f"Node '{nid}' unknown type: '{flat.type}'")
