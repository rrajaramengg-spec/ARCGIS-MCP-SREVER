"""Formatter configurations for JSON and text log output.

JSON formatter uses python-json-logger for ELK/Grafana-compatible output.
Text formatter provides human-readable output for local development.
"""

import logging

from pythonjsonlogger.json import JsonFormatter


def get_json_formatter() -> JsonFormatter:
    """Return a JSON formatter for structured log output."""
    return JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(module)s %(funcName)s %(lineno)d",
        rename_fields={
            "levelname": "level",
            "name": "logger",
            "asctime": "timestamp",
        },
        timestamp=True,
    )


def get_text_formatter() -> logging.Formatter:
    """Return a human-readable text formatter for development."""
    return logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: [req=%(request_id)s] %(message)s"
    )
