"""
Web Chat UI — demo/development only.
FastAPI app serving static HTML + WebSocket chat relay to the MCP client.
"""

import logging
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Generous timeout for complex spatial queries that involve geometry unions.
# Some queries (e.g. spatial joins with county-level polygon unions) can take
# 120+ seconds due to ArcGIS geometry service round-trips.
EXECUTE_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)

from logging_config import setup_logging

load_dotenv()
setup_logging("webchat-ui")

logger = logging.getLogger(__name__)

GIS_CLIENT_URL = os.getenv("GIS_CLIENT_URL", "http://mcp-mapgpt-client:8000")

app = FastAPI(title="GIS Chat (Demo)")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "webchat-ui"}


# ---------------------------------------------------------------------------
# WebSocket chat relay
# ---------------------------------------------------------------------------
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """Relay chat messages between browser and the MCP client."""
    await websocket.accept()
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info("WebSocket connected: %s", client_host)

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            session_id = data.get("session_id")
            logger.info("Message from %s: %s", client_host, user_message[:100])

            # Forward to MCP client
            payload = {"query": user_message}
            if session_id:
                payload["session_id"] = session_id

            try:
                async with httpx.AsyncClient(timeout=EXECUTE_TIMEOUT) as client:
                    response = await client.post(
                        f"{GIS_CLIENT_URL}/api/v1/execute",
                        json=payload,
                    )
                    result = response.json()
            except httpx.TimeoutException:
                logger.error("Timeout calling MCP client for query: %s", user_message[:100])
                result = {"error": "Request timed out. The query may involve complex spatial operations. Please try a simpler query or try again."}
            except httpx.ConnectError as exc:
                logger.error("Connection error calling MCP client: %s", exc)
                result = {"error": "Could not connect to the backend. Please try again later."}
            except Exception as exc:
                logger.error("Error calling MCP client: %s", exc)
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
    """Proxy to MCP client prompt list."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GIS_CLIENT_URL}/api/prompts")
            return response.json()
    except Exception as exc:
        logger.error("Error fetching prompts: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.get("/api/resources")
async def get_resources():
    """Proxy to MCP client resource list."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GIS_CLIENT_URL}/api/resources")
            return response.json()
    except Exception as exc:
        logger.error("Error fetching resources: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.get("/api/commands")
async def get_commands():
    """Proxy to MCP client command list."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{GIS_CLIENT_URL}/api/v1/commands"
            )
            return response.json()
    except Exception as exc:
        logger.error("Error fetching commands: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})


# ---------------------------------------------------------------------------
# Static files (served last — catch-all)
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
