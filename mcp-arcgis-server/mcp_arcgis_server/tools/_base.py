"""
Shared tool foundations: error model, exceptions, error codes, and utility functions.

All MCP tools share the error response model and utility functions defined here.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from ..arcgis.geometry import normalize_geometry

logger = logging.getLogger(__name__)

# ── Standard error codes ─────────────────────────────────────────────────

INVALID_INPUT = "INVALID_INPUT"
AUTH_REQUIRED = "AUTH_REQUIRED"
TOKEN_EXPIRED = "TOKEN_EXPIRED"
QUERY_EXECUTION_ERROR = "QUERY_EXECUTION_ERROR"
FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
LAYER_NOT_FOUND = "LAYER_NOT_FOUND"
GEOCODE_ERROR = "GEOCODE_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"


# ── Error model ──────────────────────────────────────────────────────────


class ToolError(BaseModel):
    """Standardized error response returned by all MCP tools."""

    error: str
    error_code: str
    detail: str
    tool_name: str
    retry_safe: bool = False


class ToolExecutionError(Exception):
    """Raised by tools for expected, classified failures.

    The error-handling wrapper catches this and converts it to a ToolError response.
    """

    def __init__(
        self,
        error: str,
        error_code: str,
        detail: str,
        retry_safe: bool = False,
    ) -> None:
        super().__init__(error)
        self.error = error
        self.error_code = error_code
        self.detail = detail
        self.retry_safe = retry_safe


# ── Shared utility functions ─────────────────────────────────────────────


def ensure_geometry_dict(value):
    """Convert a geometry value to a dict, accepting both str and dict.

    MCP in-process transport may deserialize JSON arguments before dispatching,
    so geometry parameters typed as ``str`` can arrive as ``dict``.  This helper
    handles both cases robustly.

    Returns:
        dict — the geometry as a Python dict.

    Raises:
        ToolExecutionError: If the value is not a valid geometry dict or JSON string.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            raise ToolExecutionError(
                error="Invalid geometry JSON",
                error_code=INVALID_INPUT,
                detail=f"Expected a JSON object, got {type(parsed).__name__}",
            )
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(
                error="Invalid geometry JSON",
                error_code=INVALID_INPUT,
                detail=f"Failed to parse geometry JSON: {exc}",
            )
    raise ToolExecutionError(
        error="Invalid geometry input",
        error_code=INVALID_INPUT,
        detail=f"Expected str or dict, got {type(value).__name__}",
    )


def parse_geometry_input(geometry_json: str) -> Dict[str, Any]:
    """Parse a JSON geometry string and normalize GeoJSON to ArcGIS JSON.

    Args:
        geometry_json: JSON string containing geometry (ArcGIS or GeoJSON format).

    Returns:
        Parsed and normalized ArcGIS JSON geometry dict.

    Raises:
        ToolExecutionError: If the input is empty, None, or invalid JSON.
    """
    if not geometry_json:
        raise ToolExecutionError(
            error="Missing geometry input",
            error_code=INVALID_INPUT,
            detail="Geometry JSON string is required but was empty or None",
        )
    geom_dict = ensure_geometry_dict(geometry_json)
    return normalize_geometry(geom_dict)


def resolve_field_name(fields: List[Dict[str, Any]], field_name: str) -> str:
    """Case-insensitive field name resolution against a layer's field list.

    Args:
        fields: List of field dicts with at least a ``"name"`` key.
        field_name: The field name to look up.

    Returns:
        The canonical field name as it appears on the layer.

    Raises:
        ToolExecutionError: If no matching field is found.
    """
    field_lower = field_name.lower()
    for field in fields:
        if field.get("name", "").lower() == field_lower:
            return field["name"]

    available = [f.get("name", "") for f in fields]
    raise ToolExecutionError(
        error="Invalid field",
        error_code=FIELD_NOT_FOUND,
        detail=f"Field '{field_name}' not found on layer. Available: {', '.join(available)}",
    )


def cap_result_count(requested: Optional[int], maximum: int) -> int:
    """Enforce a maximum result count.

    Args:
        requested: The requested count, or None for default.
        maximum: The absolute maximum allowed.

    Returns:
        The effective result count (capped at maximum).
    """
    if requested is None or requested > maximum:
        return maximum
    return requested


def format_features(
    features: List[Dict[str, Any]],
    fields: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Extract and optionally filter feature attributes.

    Args:
        features: List of feature dicts with ``"attributes"`` key.
        fields: Optional list of field names to include. If None, all fields returned.

    Returns:
        List of attribute dicts.
    """
    result = []
    for feature in features:
        attrs = feature.get("attributes", {})
        if fields is not None:
            attrs = {k: v for k, v in attrs.items() if k in fields}
        result.append(attrs)
    return result


# ── Error-handling wrapper ───────────────────────────────────────────────


def _wrap_with_error_handling(fn: Callable, tool_name: str) -> Callable:
    """Wrap a tool callable with standardized error handling and logging.

    The wrapper:
    - Logs invocation at DEBUG level
    - Logs success at INFO level
    - Catches ToolExecutionError → returns ToolError dict (WARNING)
    - Catches unexpected Exception → returns ToolError dict with INTERNAL_ERROR (ERROR)

    Args:
        fn: The async tool callable to wrap.
        tool_name: Name for error reporting and logging.

    Returns:
        Wrapped async callable with identical signature.
    """
    import functools

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        logger.debug("Tool %s invoked", tool_name)
        try:
            result = await fn(*args, **kwargs)
            logger.info("Tool %s completed successfully", tool_name)
            return result
        except ToolExecutionError as exc:
            logger.warning(
                "Tool %s expected error: [%s] %s",
                tool_name,
                exc.error_code,
                exc.error,
            )
            return ToolError(
                error=exc.error,
                error_code=exc.error_code,
                detail=exc.detail,
                tool_name=tool_name,
                retry_safe=exc.retry_safe,
            ).model_dump()
        except Exception as exc:
            logger.error(
                "Tool %s unexpected error: %s",
                tool_name,
                exc,
                exc_info=True,
            )
            return ToolError(
                error=f"{tool_name} failed",
                error_code=INTERNAL_ERROR,
                detail=str(exc),
                tool_name=tool_name,
                retry_safe=False,
            ).model_dump()

    return wrapper
