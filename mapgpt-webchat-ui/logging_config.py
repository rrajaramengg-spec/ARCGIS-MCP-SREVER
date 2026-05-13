"""
Shared logging configuration for mapgpt-webchat-ui.
Supports text (default) and JSON log format via LOG_FORMAT env var.
"""

import logging
import os


def setup_logging(service_name: str = "mapgpt-webchat-ui") -> None:
    """Configure logging for the web chat UI service.

    Args:
        service_name: Name of the service for the root logger.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "text").lower()

    handler = logging.StreamHandler()
    if log_format == "json":
        from pythonjsonlogger.json import JsonFormatter

        handler.setFormatter(JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(module)s %(funcName)s %(lineno)d",
            rename_fields={
                "levelname": "level",
                "name": "logger",
                "asctime": "timestamp",
            },
            timestamp=True,
        ))
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.getLogger(service_name).info(
        "Logging configured — level=%s format=%s", log_level, log_format
    )
