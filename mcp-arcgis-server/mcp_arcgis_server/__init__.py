"""
MCP ArcGIS Server — ArcGIS REST API operations as MCP tools.

Public API:
    create_server()       — Create a configured FastMCP server with all tools
    connect_in_process()  — Async context manager for in-process MCP transport
"""

from .server import create_server
from .transport.memory import connect_in_process

__all__ = ["create_server", "connect_in_process"]
