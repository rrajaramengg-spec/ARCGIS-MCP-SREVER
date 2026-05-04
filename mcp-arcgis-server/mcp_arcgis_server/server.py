"""
Server factory for MCP ArcGIS Server.

Creates a configured FastMCP instance with all tools registered.
"""

import logging
from typing import Tuple

from mcp.server.fastmcp import FastMCP

from .arcgis.auth import GISAuthManager
from .arcgis.client import ArcGISClient
from .config import ServerConfig
from .tools import discover_and_register

logger = logging.getLogger(__name__)


def create_server(config: ServerConfig | None = None) -> Tuple[FastMCP, ArcGISClient, GISAuthManager]:
    """Create a fully configured FastMCP server with all tools registered.

    Args:
        config: Optional ServerConfig. If None, one is created from env vars.

    Returns:
        Tuple of (FastMCP server, ArcGISClient, GISAuthManager) so the caller
        can manage the client lifecycle (e.g., call client.close() on shutdown).
    """
    if config is None:
        config = ServerConfig()

    mcp = FastMCP(
        "ArcGISServer",
        host=config.mcp_host,
        port=config.mcp_port,
    )
    # Allow Docker service hostnames and any host connecting via network
    if mcp.settings.transport_security is not None:
        mcp.settings.transport_security.allowed_hosts = ["*"]
        mcp.settings.transport_security.enable_dns_rebinding_protection = False

    auth = GISAuthManager(config)
    client = ArcGISClient(auth, config)

    # Register all tool modules via auto-discovery
    tool_count = discover_and_register(mcp, client, config)

    logger.info("Registered %d MCP tools via auto-discovery", tool_count)

    return mcp, client, auth
