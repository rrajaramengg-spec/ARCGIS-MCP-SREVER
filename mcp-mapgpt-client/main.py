"""
mcp-client — FastAPI application entry point.
Acts as MCP host/client and REST API service.
"""

import asyncio
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from logging_config import setup_logging

load_dotenv()
setup_logging("mcp-client")

logger = logging.getLogger(__name__)

# --- Module-level singletons (initialised during lifespan) ---
from core.mcp_client import MCPClient
from core.llm_service import LLMService
from core.orchestrator import Orchestrator

mcp_client = MCPClient()
llm_service = LLMService()
orchestrator: Orchestrator = None  # type: ignore[assignment]

# Rate limit state (simple in-memory per-IP counter)
_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global orchestrator

    # Initialise RAG database
    from core.rag.database import init_db as init_rag_db

    init_rag_db()
    logger.info("RAG database initialised")

    # Connect to mcp-arcgis-server (in-process by default, HTTP/SSE if URL set)
    arcgis_mcp_url = os.getenv("ARCGIS_MCP_URL", "")
    if arcgis_mcp_url and arcgis_mcp_url != "in-process":
        # HTTP/SSE transport to a remote mcp-arcgis-server
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                await mcp_client.connect(arcgis_mcp_url)
                logger.info("MCP connection established to %s", arcgis_mcp_url)
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

    orchestrator = Orchestrator(mcp_client, llm_service)
    logger.info("Orchestrator ready")

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
    title="MCP ArcGIS Client",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
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
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting
    now = time.time()
    window_start = now - 60
    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if t > window_start
    ]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_PER_MINUTE:
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
