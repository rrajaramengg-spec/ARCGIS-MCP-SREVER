"""Centralized configuration for mcp-mapgpt-client via Pydantic Settings.

Reads all environment variables from the process environment and ``.env`` file.
The module-level ``settings`` singleton is safe to import from any process
(FastAPI, Celery worker, tests) because Pydantic handles ``.env`` loading
internally — no dependency on ``load_dotenv()`` being called first.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientConfig(BaseSettings):
    """Application configuration consolidated from environment variables.

    Fields are grouped by config category (Secrets, Environment, Static).
    Required fields (no default) cause ``ValidationError`` at instantiation
    if missing from the environment — fail-fast at startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Secrets (repr=False to prevent accidental logging) ---
    azure_openai_api_key: str = Field(repr=False)

    # --- Environment Config (deployment-dependent) ---
    azure_openai_endpoint: str
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    arcgis_mcp_url: str = ""
    cors_origins: str = "http://localhost:3000"

    # --- Static Config (rarely changes) ---
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_openai_deployment: str = "gpt-5-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    llm_max_tokens: int = 4096
    embedding_dimension: int = 1536
    session_ttl_seconds: int = 7200
    max_history_turns: int = 3
    rate_limit_per_minute: int = 60
    log_level: str = "INFO"
    log_format: str = Field(default="text", description="Log format: 'text' or 'json'")
    log_correlation_enabled: bool = Field(default=True, description="Enable request correlation IDs")

    # --- Resilience / Concurrency ---
    arcgis_max_concurrent: int = Field(
        default=10,
        description="Max concurrent ArcGIS MCP tool calls (semaphore bound)",
    )
    node_retry_max_attempts: int = Field(
        default=3,
        description="Max execution attempts per graph node (1 = no retry)",
    )
    node_retry_budget: int = Field(
        default=5,
        description="Max total retries across all nodes in a single graph execution",
    )
    circuit_breaker_threshold: int = Field(
        default=5,
        description="Number of consecutive failures before circuit opens",
    )
    max_context_tokens: int = Field(
        default=4000,
        description="Max tokens for conversation history context window",
    )


settings = ClientConfig()
