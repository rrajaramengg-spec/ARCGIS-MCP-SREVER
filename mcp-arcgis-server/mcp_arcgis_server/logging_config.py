"""
Shared logging configuration for mcp-arcgis-server.
Configures structured logging using ServerConfig for log_level and log_format.
"""

import logging
from typing import Optional

from mcp_arcgis_server.config import ServerConfig


def setup_logging(
    service_name: str = "mcp-arcgis-server",
    config: Optional[ServerConfig] = None,
) -> None:
    """Configure logging for mcp-arcgis-server.

    Args:
        service_name: Name of the service for the root logger.
        config: ServerConfig instance. If None, creates a default one.
    """
    if config is None:
        config = ServerConfig()

    log_level = config.log_level.upper()
    log_format = config.log_format

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

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.getLogger(service_name).info(
        "Logging configured — level=%s format=%s", log_level, log_format
    )
