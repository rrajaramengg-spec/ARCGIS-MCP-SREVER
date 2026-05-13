"""
Centralized configuration for MCP ArcGIS Server.

Reads settings from environment variables with sensible defaults.
Uses pydantic-settings BaseSettings for validation and type coercion.
"""

from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    """Server configuration read from environment variables.

    All fields are prefixed with ``ARCGIS_`` in the environment.
    Example: ``ARCGIS_MCP_HOST=0.0.0.0``
    """

    model_config = {"env_prefix": "ARCGIS_"}

    # ── Server ───────────────────────────────────────────────────────────
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001

    # ── ArcGIS Portal / Auth ─────────────────────────────────────────────
    portal_url: str = ""
    username: str = ""
    password: str = ""
    token_url: str = ""
    server_url: str = ""
    geocode_url: str = ""
    verify_ssl: bool = True

    # ── Performance tuning ───────────────────────────────────────────────
    thread_pool_max_workers: int = 8
    layer_cache_max_size: int = 100
    default_max_results: int = 200

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "text"

    # ── Timeouts ─────────────────────────────────────────────────────────
    http_timeout: int = 30
    auth_timeout: int = 30

    # ── Tool management ──────────────────────────────────────────────────
    # Stored as str in env (comma-separated), converted to list by validator.
    tools_disabled: str = ""

    @field_validator("tools_disabled", mode="before")
    @classmethod
    def _split_tools_disabled(cls, v):
        """Accept comma-separated string and split into list."""
        if isinstance(v, list):
            return ",".join(v)
        return v

    @property
    def disabled_tools_list(self) -> List[str]:
        """Return tools_disabled as a parsed list of tool names."""
        if not self.tools_disabled:
            return []
        return [item.strip() for item in self.tools_disabled.split(",") if item.strip()]
