"""
mcp-mapgpt-client — FastAPI application entry point.
Acts as MCP host/client and REST API service.
"""

import asyncio
import logging
import time
import traceback
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from core.observability import setup_logging

from core.exceptions import ConfigurationError, ErrorResponse, MapGPTError

load_dotenv()
# Early bootstrap logging (text format, re-configured in lifespan with full config)
setup_logging("mcp-mapgpt-client")

logger = logging.getLogger(__name__)

# --- Module-level singletons (initialised during lifespan) ---
from core.mcp_client import MCPClient

mcp_client = MCPClient()  # re-created with config during lifespan
orchestrator = None  # type: ignore[assignment]

# Rate limit state (simple in-memory per-IP counter)
_rate_limit_store: dict[str, list[float]] = {}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global orchestrator

    # --- Validate configuration ---
    from core.config import ClientConfig

    try:
        config = ClientConfig()
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid configuration — {exc.error_count()} error(s): {exc}"
        ) from exc

    from core import providers

    providers.set_config(config)

    # --- Re-create MCP client with config ---
    global mcp_client
    mcp_client = MCPClient(arcgis_max_concurrent=config.arcgis_max_concurrent)

    # --- Re-configure logging with full config ---
    setup_logging(
        service_name="mcp-mapgpt-client",
        log_level=config.log_level,
        log_format=config.log_format,
        correlation_enabled=config.log_correlation_enabled,
    )

    # --- Initialise services with config injection ---
    from core.llm_service import LLMService
    from core.rag.database import init_db as init_rag_db
    from core.rag.embeddings.service import get_embedding_service

    llm_service = LLMService(config)
    get_embedding_service(config)
    init_rag_db(config.database_url)
    logger.info("RAG database initialised")

    # Connect to mcp-arcgis-server (in-process by default, HTTP/SSE if URL set)
    if config.arcgis_mcp_url and config.arcgis_mcp_url != "in-process":
        # HTTP/SSE transport to a remote mcp-arcgis-server
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                await mcp_client.connect(config.arcgis_mcp_url)
                logger.info("MCP connection established to %s", config.arcgis_mcp_url)
                break
            except Exception as exc:
                logger.warning(
                    "MCP connection attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                else:
                    logger.error(
                        "Could not connect to mcp-arcgis-server after %d attempts — running degraded",
                        max_retries,
                    )
    else:
        # In-process transport (default)
        try:
            await mcp_client.connect_in_process()
            logger.info("MCP in-process connection established")
        except Exception as exc:
            logger.error(
                "Failed to start in-process MCP transport — running degraded: %s", exc
            )

    from core.rag.service import RAGService
    from core.orchestrator import MapGPTOrchestrator

    rag_service = RAGService()
    providers.set_rag_service(rag_service)

    from core.config import settings
    orchestrator = MapGPTOrchestrator(mcp_client, llm_service, rag_service=rag_service, config=settings)
    providers.set_orchestrator(orchestrator)
    logger.info("MapGPTOrchestrator ready")

    yield

    # Shutdown
    await mcp_client.disconnect()
    from core.rag.database import close_db

    await close_db()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MapGPT Client",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — reads from config singleton for values needed before lifespan
from core.config import settings as _settings

cors_origins = _settings.cors_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware: request logging + rate limiting
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_and_rate_limit(request: Request, call_next):
    """Log requests/responses and enforce rate limiting."""
    # Re-establish correlation ContextVar — BaseHTTPMiddleware runs this
    # function in a separate anyio task that does not inherit the parent's
    # ContextVar modifications.  The outer CorrelationMiddleware stores the
    # ID in scope["state"] so we can retrieve it here.
    _rid = request.scope.get("state", {}).get("_correlation_id")
    if _rid:
        from core.observability.context import request_id_var

        request_id_var.set(_rid)

    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting
    now = time.time()
    window_start = now - 60
    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if t > window_start
    ]
    if len(_rate_limit_store[client_ip]) >= _settings.rate_limit_per_minute:
        logger.warning("Rate limit exceeded for %s", client_ip)
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"},
        )
    _rate_limit_store[client_ip].append(now)

    # Process request with timing
    start = time.time()
    response = await call_next(request)
    latency_ms = (time.time() - start) * 1000

    logger.info(
        "%s %s → %d (%.0f ms)",
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
    )
    return response


# Correlation middleware — must be added AFTER @app.middleware("http") so that
# insert(0, ...) puts it at the front of user_middleware.  After reversal in
# build_middleware_stack this becomes the outermost wrapper, ensuring the
# correlation ID is available in scope["state"] before any inner middleware runs.
if _settings.log_correlation_enabled:
    from core.observability.middleware import CorrelationMiddleware

    app.add_middleware(CorrelationMiddleware)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error: %s", exc.errors())
    # Build serializable error details — exc.errors() may contain non-serializable
    # objects (e.g. ValueError instances in ctx).
    detail = []
    for err in exc.errors():
        safe = {k: v for k, v in err.items() if k != "ctx"}
        if "ctx" in err:
            safe["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
        detail.append(safe)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation Error", "detail": detail},
    )


@app.exception_handler(MapGPTError)
async def mapgpt_error_handler(request: Request, exc: MapGPTError):
    """Structured handler for MapGPTError hierarchy.

    4xx logged as WARNING, 5xx as ERROR with traceback.
    """
    if exc.status_code >= 500:
        logger.error(
            "MapGPTError [%s] %s\n%s", exc.code, exc.message, traceback.format_exc()
        )
    else:
        logger.warning("MapGPTError [%s] %s", exc.code, exc.message)
    body = ErrorResponse(
        error=exc.message,
        code=exc.code,
        detail=getattr(exc, "tool_name", None) or None,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(exclude_none=True),
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    if mcp_client.is_connected:
        return {"status": "ok", "version": "1.0.0"}
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "detail": "mcp-arcgis-server"},
    )


# ---------------------------------------------------------------------------
# Register API routes
# ---------------------------------------------------------------------------
from api.routes import router

app.include_router(router)
