"""
Dynamic tool registry for MCP ArcGIS Server.

Provides decorator-based tool registration and auto-discovery,
replacing manual per-module `register()` calls.
"""

import functools
import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from ..arcgis.client import ArcGISClient
from ..config import ServerConfig
from ._base import _wrap_with_error_handling

logger = logging.getLogger(__name__)

# ── Tool definition ──────────────────────────────────────────────────────

_TOOL_REGISTRY: List["ToolDefinition"] = []


@dataclass
class ToolDefinition:
    """Metadata for a registered tool function."""

    name: str
    description: str
    fn: Callable
    module: str


# ── Decorator ────────────────────────────────────────────────────────────


def register_tool(name: str, description: str) -> Callable:
    """Decorator that registers a tool function for auto-discovery.

    The decorated function should have ``client: ArcGISClient`` as its first
    parameter. At registration time, ``client`` will be bound via partial and
    the parameter removed from the exposed MCP schema.

    Args:
        name: MCP tool name (e.g. ``"query_features"``).
        description: Human-readable tool description for the MCP schema.
    """

    def decorator(fn: Callable) -> Callable:
        _TOOL_REGISTRY.append(
            ToolDefinition(
                name=name,
                description=description,
                fn=fn,
                module=fn.__module__,
            )
        )
        return fn

    return decorator


def get_registered_tools() -> List[ToolDefinition]:
    """Return a copy of all registered tool definitions."""
    return list(_TOOL_REGISTRY)


# ── Client binding ───────────────────────────────────────────────────────


def _bind_client(fn: Callable, client: ArcGISClient) -> Callable:
    """Bind ``client`` to the first parameter and rewrite the signature.

    Returns a ``functools.partial`` with the ``client`` parameter removed
    from ``__signature__`` so FastMCP's ``func_metadata`` does not expose it
    in the JSON schema.
    """
    bound = functools.partial(fn, client)

    # Rewrite signature to exclude ``client``
    sig = inspect.signature(fn)
    new_params = [p for p in sig.parameters.values() if p.name != "client"]
    bound.__signature__ = sig.replace(parameters=new_params)

    # Preserve introspection attributes
    bound.__name__ = fn.__name__
    bound.__doc__ = fn.__doc__
    bound.__module__ = fn.__module__
    # Preserve type annotations (excluding client) so FastMCP can detect
    # injected parameters like ctx: Context via typing.get_type_hints().
    bound.__annotations__ = {
        k: v for k, v in getattr(fn, "__annotations__", {}).items()
        if k != "client"
    }

    return bound


# ── Auto-import ──────────────────────────────────────────────────────────


def _auto_import_tool_modules() -> None:
    """Import all public modules in the ``tools`` package.

    Modules whose name starts with ``_`` are skipped (e.g. ``_base``, ``_registry``).
    Importing triggers ``@register_tool`` decorators to populate ``_TOOL_REGISTRY``.
    """
    import mcp_arcgis_server.tools as tools_pkg

    for importer, modname, ispkg in pkgutil.walk_packages(
        tools_pkg.__path__,
        prefix=tools_pkg.__name__ + ".",
    ):
        short_name = modname.rsplit(".", 1)[-1]
        if short_name.startswith("_"):
            continue
        try:
            importlib.import_module(modname)
            logger.debug("Imported tool module: %s", modname)
        except Exception:
            logger.error("Failed to import tool module: %s", modname, exc_info=True)


# ── Discovery and registration ───────────────────────────────────────────


def discover_and_register(
    mcp: FastMCP,
    client: ArcGISClient,
    config: ServerConfig,
) -> int:
    """Auto-discover tool modules, bind client, wrap with error handling, and register on FastMCP.

    Args:
        mcp: The FastMCP server instance.
        client: The ArcGIS client to inject into each tool.
        config: Server configuration (used for ``tools_disabled``).

    Returns:
        Number of tools registered.
    """
    _auto_import_tool_modules()

    disabled = set(config.disabled_tools_list)
    registered = 0

    for tool_def in _TOOL_REGISTRY:
        if tool_def.name in disabled:
            logger.info("Tool '%s' is disabled via config — skipping", tool_def.name)
            continue

        bound_fn = _bind_client(tool_def.fn, client)
        wrapped_fn = _wrap_with_error_handling(bound_fn, tool_def.name)

        mcp.add_tool(
            wrapped_fn,
            name=tool_def.name,
            description=tool_def.description,
        )
        registered += 1
        logger.debug("Registered tool: %s", tool_def.name)

    logger.info("Registered %d MCP tools", registered)
    return registered
