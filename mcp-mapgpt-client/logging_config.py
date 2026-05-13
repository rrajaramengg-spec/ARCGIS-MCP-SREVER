"""
Shared logging configuration — delegates to core.observability.

Retained as a thin wrapper for backward compatibility with existing
``from logging_config import setup_logging`` imports.
"""

from core.observability import setup_logging

__all__ = ["setup_logging"]
