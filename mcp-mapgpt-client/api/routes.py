"""
API router for /api/v1/ endpoints.
"""

import asyncio
import json as json_module
import logging
import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    FeedbackRequest,
    FeedbackResponse,
    IngestRequest,
    IngestResponse,
    LocateRequest,
    LocateResponse,
    SummarizeResponse,
    SummarizeStatResponse,
)
from core.rag import ingest_layers, ingest_query_patterns
from core.response_cache import ResponseCache
from core.session import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# --- Slash command registry ---
COMMANDS = [
    {
        "name": "/locate",
        "description": "Geocode an address or reverse-geocode coordinates",
        "endpoint": "/api/v1/locate",
        "params": "<address> or <lat,lon>",
    },
    {
        "name": "/summarize",
        "description": "Execute a query and return an LLM-generated summary",
        "endpoint": "/api/v1/summarize",
        "params": "<natural language query>",
    },
    {
        "name": "/summarize-stat",
        "description": "Compute field statistics and return an LLM summary",
        "endpoint": "/api/v1/summarize-stat",
        "params": "<natural language query about a field>",
    },
    {
        "name": "/arcgis-execute",
        "description": "Direct ArcGIS tool execution — fast, no RAG planning",
        "endpoint": "/api/v1/arcgis-execute",
        "params": "<natural language query>",
    },
]


@router.get("/commands")
async def list_commands():
    """Return the list of available slash commands."""
    return COMMANDS


@router.post("/query")
async def query_plan(request: ExecuteRequest):
    """Generate a query plan via RAG + LLM without executing against ArcGIS."""
    from main import orchestrator  # Lazy import to avoid circular

    logger.info("Query request — query=%s", request.query[:100])

    if request.session_id:
        await SessionManager.ensure_session(request.session_id)

    try:
        result = await orchestrator.plan(
            query=request.query,
            session_id=request.session_id,
        )
        return result
    except Exception as exc:
        logger.error("Query error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(exc)},
        )


@router.post("/execute", response_model=ExecuteResponse)
async def execute_query(request: ExecuteRequest):
    """Execute a natural language query through the full pipeline (RAG → LLM → MCP tool → raw ArcGIS data)."""
    from main import orchestrator  # Lazy import to avoid circular

    logger.info("Execute request — query=%s", request.query[:100])

    if request.session_id:
        await SessionManager.ensure_session(request.session_id)

    try:
        result = await orchestrator.execute(
            query=request.query,
            session_id=request.session_id,
        )
        return result
    except Exception as exc:
        logger.error("Execute error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(exc)},
        )


@router.post("/execute/stream")
async def execute_query_stream(request: ExecuteRequest):
    """Execute a query with SSE progress streaming."""
    from main import orchestrator

    logger.info("Execute/stream request — query=%s", request.query[:100])

    if request.session_id:
        await SessionManager.ensure_session(request.session_id)

    progress_queue: asyncio.Queue = asyncio.Queue()

    async def progress_callback(progress: float, total: float | None, message: str | None) -> None:
        await progress_queue.put({"step": message, "current": progress, "total": total})

    async def event_generator():
        task = asyncio.create_task(
            orchestrator.execute(
                query=request.query,
                session_id=request.session_id,
                progress_callback=progress_callback,
            )
        )

        while not task.done():
            try:
                item = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                yield f"event: progress\ndata: {json_module.dumps(item)}\n\n"
            except asyncio.TimeoutError:
                continue

        # Drain remaining progress events
        while not progress_queue.empty():
            item = await progress_queue.get()
            yield f"event: progress\ndata: {json_module.dumps(item)}\n\n"

        try:
            result = task.result()
            yield f"event: result\ndata: {json_module.dumps(result)}\n\n"
        except Exception as exc:
            logger.error("Execute/stream error: %s", exc)
            yield f"event: error\ndata: {json_module.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/arcgis-execute", response_model=ExecuteResponse)
async def arcgis_execute(request: ExecuteRequest):
    """Direct ArcGIS tool execution — LLM selects and invokes MCP tools without RAG planning."""
    from main import orchestrator  # Lazy import to avoid circular

    logger.info("ArcGIS execute request — query=%s", request.query[:100])

    try:
        result = await orchestrator.arcgis_execute(
            query=request.query,
            session_id=request.session_id,
        )
        return result
    except Exception as exc:
        logger.error("ArcGIS execute error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(exc)},
        )


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_query(request: ExecuteRequest):
    """Execute a query and return an LLM-generated natural language summary of the results."""
    from main import orchestrator  # Lazy import to avoid circular

    logger.info("Summarize request — query=%s", request.query[:100])

    try:
        result = await orchestrator.summarize(
            query=request.query,
            session_id=request.session_id,
        )
        return result
    except Exception as exc:
        logger.error("Summarize error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(exc)},
        )


@router.post("/locate", response_model=LocateResponse)
async def locate(request: LocateRequest):
    """Geocode an address or reverse-geocode coordinates directly (no LLM planning)."""
    from main import orchestrator  # Lazy import to avoid circular

    logger.info("Locate request — address=%s lat=%s lon=%s", request.address, request.latitude, request.longitude)

    try:
        result = await orchestrator.locate(
            address=request.address,
            latitude=request.latitude,
            longitude=request.longitude,
        )
        return result
    except Exception as exc:
        logger.error("Locate error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(exc)},
        )


@router.post("/summarize-stat", response_model=SummarizeStatResponse)
async def summarize_stat(request: ExecuteRequest):
    """Compute field statistics for a layer and return an LLM-generated summary."""
    from main import orchestrator  # Lazy import to avoid circular

    logger.info("Summarize-stat request — query=%s", request.query[:100])

    try:
        result = await orchestrator.summarize_stat(
            query=request.query,
            session_id=request.session_id,
        )
        return result
    except Exception as exc:
        logger.error("Summarize-stat error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(exc)},
        )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_doc(request: IngestRequest):
    """Ingest data into the RAG knowledge base."""
    logger.info("Ingest request — doc_type=%s, items=%d", request.doc_type, len(request.data))

    try:
        if request.doc_type == "layer":
            result = await ingest_layers(request.data)
            return IngestResponse(
                status="ingested",
                layers=result.get("layers"),
                fields=result.get("fields"),
            )
        elif request.doc_type == "query_pattern":
            result = await ingest_query_patterns(
                request.data, replace=request.replace
            )
            return IngestResponse(
                status="ingested",
                patterns=result.get("patterns"),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid doc_type '{request.doc_type}'. Must be 'layer' or 'query_pattern'.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ingest error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(exc)},
        )


@router.post("/user-feedback", response_model=FeedbackResponse)
async def user_feedback(request: FeedbackRequest):
    """Accept user feedback (thumbs up/down) and apply to response cache."""
    logger.info(
        "Feedback request — session=%s query=%s feedback=%s",
        request.session_id, request.query_id, request.feedback,
    )

    cache_key = await ResponseCache.get_cache_key_for_query(
        request.session_id, request.query_id
    )
    if cache_key is None:
        return FeedbackResponse(status="ok", action="no_cache_entry")

    if request.feedback == "up":
        await ResponseCache.promote(cache_key)
        return FeedbackResponse(status="ok", action="promoted")

    # feedback == "down"
    action = await ResponseCache.evict(cache_key)
    return FeedbackResponse(status="ok", action=action)
