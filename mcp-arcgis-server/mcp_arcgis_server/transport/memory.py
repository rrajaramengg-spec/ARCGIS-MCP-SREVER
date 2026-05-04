"""
In-process memory stream transport for MCP ArcGIS Server.

Uses anyio memory object streams to wire ClientSession ↔ Server
with zero network overhead. For use when mcp-arcgis-server is imported
as a library (in-process) rather than accessed via HTTP/SSE.

NOTE: Uses FastMCP._mcp_server private API. Pinned to mcp>=1.8.0,<2.0.0.
If this breaks after an SDK upgrade, update _get_low_level_server().
See: mcp/server/fastmcp/server.py run_stdio_async() for reference pattern.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import anyio
from mcp.client.session import ClientSession
from mcp.server.fastmcp import FastMCP


def _get_low_level_server(mcp: FastMCP):
    """Access the underlying MCP Server instance.

    Risk isolation: all _mcp_server access goes through this single function.
    If the private API changes in a future MCP SDK version, only this
    function needs updating.
    """
    return mcp._mcp_server


@asynccontextmanager
async def connect_in_process(server: FastMCP) -> AsyncIterator[ClientSession]:
    """Create an in-process MCP client session connected to a FastMCP server.

    Yields a ready-to-use ClientSession connected via anyio memory streams.
    The server task is automatically cancelled on context exit.

    Usage:
        mcp, client, auth = create_server()
        await auth.initialize()
        async with connect_in_process(mcp) as session:
            tools = await session.list_tools()
            result = await session.call_tool("query_features", {...})
    """
    low_level = _get_low_level_server(server)

    # Create paired memory streams:
    # client writes → server reads, server writes → client reads
    server_read_writer, server_read = anyio.create_memory_object_stream(0)
    server_write, server_write_reader = anyio.create_memory_object_stream(0)

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            low_level.run,
            server_read,
            server_write,
            low_level.create_initialization_options(),
        )
        async with ClientSession(server_write_reader, server_read_writer) as session:
            await session.initialize()
            yield session
            tg.cancel_scope.cancel()
