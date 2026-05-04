"""
Shared logging configuration.
Configures structured logging with LOG_LEVEL env var support.
"""

import logging
import os


def setup_logging(service_name: str = "mcp-arcgis") -> None:
    """Configure logging for a service module.

    Args:
        service_name: Name of the service for the root logger.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logger = logging.getLogger(service_name)
    logger.info("Logging configured at %s level for %s", log_level, service_name)
