"""
MapGPT Web Chat UI — demo/development only.
FastAPI app serving React SPA + WebSocket chat relay to mcp-mapgpt-client.
"""

import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Generous timeout for complex spatial queries that involve geometry unions.
# Some queries (e.g. spatial joins with county-level polygon unions) can take
# 120+ seconds due to ArcGIS geometry service round-trips.
EXECUTE_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)

from logging_config import setup_logging

load_dotenv()
setup_logging("mapgpt-webchat-ui")

logger = logging.getLogger(__name__)

MAPGPT_CLIENT_URL = os.getenv("MAPGPT_CLIENT_URL", "http://mcp-mapgpt-client:8000")

app = FastAPI(title="MapGPT Web Chat (Demo)")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "mapgpt-webchat-ui"}


# ---------------------------------------------------------------------------
# WebSocket chat relay
# ---------------------------------------------------------------------------
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """Relay chat messages between browser and mcp-mapgpt-client."""
    await websocket.accept()
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info("WebSocket connected: %s", client_host)

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            session_id = data.get("session_id")
            logger.info("Message from %s: %s", client_host, user_message[:100])

            # Forward to mcp-mapgpt-client
            payload = {"query": user_message}
            if session_id:
                payload["session_id"] = session_id

            try:
                async with httpx.AsyncClient(timeout=EXECUTE_TIMEOUT) as client:
                    response = await client.post(
                        f"{MAPGPT_CLIENT_URL}/api/mapgpt/v1/execute",
                        json=payload,
                    )
                    result = response.json()
            except httpx.TimeoutException:
                logger.error("Timeout calling mcp-mapgpt-client for query: %s", user_message[:100])
                result = {"error": "Request timed out. The query may involve complex spatial operations. Please try a simpler query or try again."}
            except httpx.ConnectError as exc:
                logger.error("Connection error calling mcp-mapgpt-client: %s", exc)
                result = {"error": "Could not connect to the MapGPT backend. Please try again later."}
            except Exception as exc:
                logger.error("Error calling mcp-mapgpt-client: %s", exc)
                err_msg = str(exc).strip()
                result = {"error": err_msg or f"Unexpected error: {type(exc).__name__}"}

            await websocket.send_json({"type": "response", "data": result})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", client_host)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)


# ---------------------------------------------------------------------------
# Proxy routes
# ---------------------------------------------------------------------------
@app.get("/api/prompts")
async def get_prompts():
    """Proxy to mcp-mapgpt-client prompt list."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{MAPGPT_CLIENT_URL}/api/prompts")
            return response.json()
    except Exception as exc:
        logger.error("Error fetching prompts: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.get("/api/resources")
async def get_resources():
    """Proxy to mcp-mapgpt-client resource list."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{MAPGPT_CLIENT_URL}/api/resources")
            return response.json()
    except Exception as exc:
        logger.error("Error fetching resources: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.get("/api/commands")
async def get_commands():
    """Proxy to mcp-mapgpt-client command list."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{MAPGPT_CLIENT_URL}/api/mapgpt/v1/commands"
            )
            return response.json()
    except Exception as exc:
        logger.error("Error fetching commands: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.post("/api/user-feedback")
async def user_feedback(request: Request):
    """Proxy user feedback (thumbs up/down) to mcp-mapgpt-client."""
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{MAPGPT_CLIENT_URL}/api/mapgpt/v1/user-feedback",
                json=body,
            )
            if response.status_code >= 400:
                logger.error("Feedback upstream error: HTTP %s", response.status_code)
                return JSONResponse(
                    status_code=502,
                    content={"error": f"Upstream returned HTTP {response.status_code}"},
                )
            return response.json()
    except Exception as exc:
        logger.error("Error proxying user-feedback: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})


# ---------------------------------------------------------------------------
# Static files — serve React SPA from dist/ or fallback to legacy static/
# ---------------------------------------------------------------------------
_dist_dir = Path(__file__).parent / "dist"
_static_dir = Path(__file__).parent / "static"

if _dist_dir.is_dir() and (_dist_dir / "index.html").exists():
    # Serve Vite-built assets from dist/assets/
    app.mount("/assets", StaticFiles(directory=str(_dist_dir / "assets")), name="assets")

    # Serve legacy diagnostic page if copied via public/
    if (_dist_dir / "diag.html").exists():

        @app.get("/diag.html")
        async def diag():
            return FileResponse(str(_dist_dir / "diag.html"))

    # SPA catch-all: serve dist/index.html for all non-API, non-WS routes
    @app.get("/{path:path}")
    async def spa_catch_all(path: str):
        file_path = _dist_dir / path
        if path and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_dist_dir / "index.html"))
else:
    # Fallback: serve legacy static files
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
