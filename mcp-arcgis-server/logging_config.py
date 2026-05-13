"""
Root-level logging configuration — delegates to mcp_arcgis_server.logging_config.

Retained for backward compatibility with imports from the package root.
"""

from mcp_arcgis_server.logging_config import setup_logging

__all__ = ["setup_logging"]
