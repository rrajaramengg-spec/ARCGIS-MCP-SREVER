"""IMCPClient protocol — behavioral contract for MCP client connections."""

from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IMCPClient(Protocol):
    """Protocol for MCP (Model Context Protocol) clients.

    Implementations must provide connection management, tool listing,
    and tool execution capabilities.
    """

    @property
    def is_connected(self) -> bool:
        """Whether the client is currently connected to an MCP server."""
        ...

    async def connect(self, base_url: str) -> None:
        """Connect to a remote MCP server via HTTP/SSE.

        Args:
            base_url: Base URL of the MCP server.
        """
        ...

    async def connect_in_process(self) -> None:
        """Connect to an in-process MCP server (stdio transport)."""
        ...

    async def disconnect(self) -> None:
        """Disconnect from the MCP server and release resources."""
        ...

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server.

        Returns:
            List of tool definitions with name, description, and schema.
        """
        ...

    async def call_tool(
        self,
        name: str,
        args: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
    ) -> Any:
        """Execute a tool on the MCP server.

        Args:
            name: Tool name to invoke.
            args: Arguments to pass to the tool.
            progress_callback: Optional callback for progress reporting.

        Returns:
            Tool execution result.
        """
        ...
