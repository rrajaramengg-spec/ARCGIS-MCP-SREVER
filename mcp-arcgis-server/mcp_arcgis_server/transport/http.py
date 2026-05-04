"""
HTTP/SSE transport for standalone MCP ArcGIS Server deployment.

Creates a Starlette ASGI app with /health and SSE endpoints.
Requires the [http] optional dependency group (starlette, uvicorn).
"""

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route


async def health_endpoint(request):
    return JSONResponse({"status": "ok", "service": "mcp-arcgis-server"})


def create_app(server: FastMCP) -> Starlette:
    """Create a Starlette app with /health and MCP SSE endpoints."""
    sse_app = server.sse_app()
    return Starlette(
        routes=[
            Route("/health", health_endpoint, methods=["GET"]),
            Mount("/", app=sse_app),
        ],
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=["*"]),
        ],
    )
