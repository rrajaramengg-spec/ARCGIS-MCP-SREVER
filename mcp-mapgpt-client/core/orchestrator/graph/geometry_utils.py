"""Client-side geometry union utilities.

Duplicated from ``mcp_arcgis_server/arcgis/geometry.py`` to avoid
cross-service imports.  Pure computation — no I/O, no MCP calls.

A parity test (``test_geometry_utils_parity.py``) ensures these copies
produce identical output to the canonical version.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_UNION_FEATURES = 500

_GEOM_TYPE_KEYS = {
    "rings": "polygon",
    "paths": "polyline",
    "points": "multipoint",
}


def _classify_geometry(geom: Dict[str, Any]) -> str:
    """Return a type label for an ArcGIS JSON geometry dict."""
    if "x" in geom and "y" in geom:
        return "point"
    for key, label in _GEOM_TYPE_KEYS.items():
        if key in geom:
            return label
    return "unknown"


def _fallback_ring_merge(
    geometries: List[Dict[str, Any]],
    sr: int = 4326,
) -> Optional[Dict[str, Any]]:
    """Client-side fallback union via ring/path/point merge.

    Concatenates all rings (polygons), paths (polylines),
    or points (multipoints) into a single multi-part geometry.
    Does NOT dissolve shared boundaries, but works as a
    spatial filter envelope without a geometry service.
    """
    geom_type = _classify_geometry(geometries[0])

    if geom_type == "polygon":
        all_rings: List[Any] = []
        for g in geometries:
            all_rings.extend(g.get("rings", []))
        if not all_rings:
            return None
        return {"rings": all_rings, "spatialReference": {"wkid": sr}}

    if geom_type == "polyline":
        all_paths: List[Any] = []
        for g in geometries:
            all_paths.extend(g.get("paths", []))
        if not all_paths:
            return None
        return {"paths": all_paths, "spatialReference": {"wkid": sr}}

    if geom_type in ("multipoint", "point"):
        all_points: List[Any] = []
        for g in geometries:
            if "points" in g:
                all_points.extend(g["points"])
            elif "x" in g and "y" in g:
                all_points.append([g["x"], g["y"]])
        if not all_points:
            return None
        return {"points": all_points, "spatialReference": {"wkid": sr}}

    logger.error("Fallback merge unsupported for geometry type: %s", geom_type)
    return None


def union_feature_geometries(
    features: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Extract and union all geometries from a list of ArcGIS feature dicts.

    Uses client-side ring/path merge (instant, no network) which is
    sufficient for spatial filter use cases.

    Args:
        features: List of ArcGIS feature dicts, each optionally containing
            a ``"geometry"`` key with an ArcGIS JSON geometry dict.

    Returns:
        Unified ArcGIS JSON geometry dict, or ``None`` if no geometries found.

    Raises:
        ValueError: If features contain mixed geometry types.
    """
    geometries = [f["geometry"] for f in features if f.get("geometry")]

    if not geometries:
        return None

    if len(geometries) == 1:
        return geometries[0]

    # Validate homogeneous geometry types.
    types = {_classify_geometry(g) for g in geometries}
    if len(types) > 1:
        raise ValueError(
            f"Cannot union mixed geometry types: {', '.join(sorted(types))}. "
            "All features must have the same geometry type."
        )

    if len(geometries) > MAX_UNION_FEATURES:
        logger.warning(
            "union_feature_geometries: truncating %d geometries to %d",
            len(geometries),
            MAX_UNION_FEATURES,
        )
        geometries = geometries[:MAX_UNION_FEATURES]

    sr = geometries[0].get("spatialReference", {}).get("wkid", 4326)

    merged = _fallback_ring_merge(geometries, sr)
    if merged is not None:
        return merged

    # ring merge failed — no server-side fallback in client copy
    logger.warning(
        "Ring merge failed for %d geometries, returning None",
        len(geometries),
    )
    return None
