"""
CLI entry point for mcp-arcgis-server.

Starts the HTTP/SSE MCP server for standalone deployment.
Invocable via `mcp-arcgis-server` (console script) or `python -m mcp_arcgis_server`.
"""

import logging

from dotenv import load_dotenv


def cli():
    """Start the MCP ArcGIS Server with HTTP/SSE transport."""
    load_dotenv()

    from .config import ServerConfig
    config = ServerConfig()

    from .logging_config import setup_logging
    setup_logging("mcp-arcgis-server", config=config)

    logger = logging.getLogger(__name__)

    from .server import create_server
    from .transport.http import create_app

    server, _client, _auth = create_server(config)
    app = create_app(server)

    logger.info("Starting MCP ArcGIS Server on %s:%d", config.mcp_host, config.mcp_port)

    import uvicorn
    uvicorn.run(app, host=config.mcp_host, port=config.mcp_port)


if __name__ == "__main__":
    cli()
