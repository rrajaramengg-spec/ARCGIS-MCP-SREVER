"""Centralized observability infrastructure for mcp-mapgpt-client.

Public API:
    setup_logging(service_name, log_level, log_format, correlation_enabled)
    get_request_id() -> str
"""

import logging

from core.observability.context import request_id_var, service_name_var
from core.observability.filters import CorrelationFilter, SanitizingFilter
from core.observability.formatters import get_json_formatter, get_text_formatter

_NOISY_LOGGERS = ("httpx", "httpcore", "uvicorn.access")


def setup_logging(
    service_name: str = "mapgpt",
    log_level: str = "INFO",
    log_format: str = "text",
    correlation_enabled: bool = True,
) -> None:
    """Configure logging with structured output and optional correlation.

    Args:
        service_name: Identifies the service in log records.
        log_level: Root logger level (INFO, DEBUG, etc.).
        log_format: 'text' for human-readable, 'json' for structured output.
        correlation_enabled: Whether to attach CorrelationFilter.
    """
    service_name_var.set(service_name)
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Build handler with appropriate formatter
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(get_json_formatter())
    else:
        handler.setFormatter(get_text_formatter())

    # Attach filters
    if correlation_enabled:
        handler.addFilter(CorrelationFilter())
    handler.addFilter(SanitizingFilter())

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger(service_name).info(
        "Logging configured — level=%s format=%s correlation=%s",
        log_level.upper(),
        log_format,
        correlation_enabled,
    )


def get_request_id() -> str:
    """Return the current correlation ID or '-' if none is set."""
    return request_id_var.get()
