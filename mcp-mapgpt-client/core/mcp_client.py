"""
MCP client for connecting to MCP servers via HTTP/SSE transport.
Manages ClientSession lifecycle via AsyncExitStack.
"""

import logging
from contextlib import AsyncExitStack
from typing import Any, Callable, Dict, List, Optional

from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for connecting to an MCP server over HTTP/SSE."""

    def __init__(self) -> None:
        self._exit_stack: Optional[AsyncExitStack] = None
        self._session: Optional[ClientSession] = None
        self._base_url: Optional[str] = None
        self._arcgis_client: Optional[Any] = None  # For in-process transport cleanup

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def connect(self, base_url: str) -> None:
        """Connect to an MCP server.

        Args:
            base_url: The SSE endpoint URL (e.g. http://host:port/sse).

        Raises:
            ConnectionError: If the server is unreachable.
        """
        self._base_url = base_url
        try:
            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()

            streams = await self._exit_stack.enter_async_context(sse_client(base_url))
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(*streams)
            )
            await self._session.initialize()

            logger.info("Connected to MCP server at %s", base_url)
        except Exception as exc:
            await self.disconnect()
            raise ConnectionError(
                f"Failed to connect to MCP server at {base_url}: {exc}"
            ) from exc

    async def connect_in_process(self) -> None:
        """Connect to mcp-arcgis-server via in-process memory transport.

        Creates a FastMCP server instance in the same process and connects
        via anyio memory streams. Zero network overhead.
        """
        try:
            from mcp_arcgis_server import create_server, connect_in_process

            mcp_server, self._arcgis_client, auth = create_server()
            await auth.initialize()

            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()

            ctx = connect_in_process(mcp_server)
            self._session = await self._exit_stack.enter_async_context(ctx)

            logger.info("Connected to MCP server via in-process transport")
        except Exception as exc:
            await self.disconnect()
            raise ConnectionError(
                f"Failed to connect via in-process transport: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        """Disconnect from the MCP server and release resources."""
        if self._arcgis_client:
            try:
                self._arcgis_client.close()
            except Exception as exc:
                logger.warning("Error closing ArcGIS client: %s", exc)
            self._arcgis_client = None
        if self._exit_stack:
            try:
                await self._exit_stack.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("Error during MCP disconnect: %s", exc)
            finally:
                self._exit_stack = None
                self._session = None
                logger.info("Disconnected from MCP server")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools on the connected server.

        Returns:
            List of tool definitions with name, description, and inputSchema.
        """
        if not self._session:
            raise ConnectionError("Not connected to MCP server")

        result = await self._session.list_tools()
        tools = []
        for tool in result.tools:
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                }
            )
        logger.debug("Listed %d tools from MCP server", len(tools))
        return tools

    async def call_tool(
        self,
        name: str,
        args: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
    ) -> Any:
        """Call a tool on the connected server.

        Args:
            name: Tool name.
            args: Tool arguments dict.
            progress_callback: Optional async callback receiving (progress, total, message).

        Returns:
            Tool result content.
        """
        if not self._session:
            raise ConnectionError("Not connected to MCP server")

        logger.debug("Calling MCP tool: %s with args: %s", name, args)
        call_kwargs: Dict[str, Any] = {"arguments": args}
        if progress_callback is not None:
            call_kwargs["progress_callback"] = progress_callback
        result = await self._session.call_tool(name, **call_kwargs)

        # Check for MCP-level error flag
        if getattr(result, "isError", False):
            logger.error("MCP tool %s returned isError=True", name)

        # Extract content from MCP result
        if result.content:
            # Return the text content from the first content block
            for block in result.content:
                if hasattr(block, "text"):
                    import json

                    try:
                        parsed = json.loads(block.text)
                        return parsed
                    except (json.JSONDecodeError, TypeError) as exc:
                        logger.error(
                            "MCP tool %s: json.loads failed (%s), raw text: %.500s",
                            name, exc, block.text,
                        )
                        return block.text
        logger.warning("MCP tool %s returned no content", name)
        return None

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List available prompts."""
        if not self._session:
            raise ConnectionError("Not connected to MCP server")

        result = await self._session.list_prompts()
        return [
            {"name": p.name, "description": p.description or ""} for p in result.prompts
        ]

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available resources."""
        if not self._session:
            raise ConnectionError("Not connected to MCP server")

        result = await self._session.list_resources()
        return [
            {
                "uri": str(r.uri),
                "name": r.name or "",
                "description": r.description or "",
            }
            for r in result.resources
        ]

    async def read_resource(self, uri: str) -> Any:
        """Read a resource by URI."""
        if not self._session:
            raise ConnectionError("Not connected to MCP server")

        result = await self._session.read_resource(uri)
        if result.contents:
            for block in result.contents:
                if hasattr(block, "text"):
                    return block.text
        return None
