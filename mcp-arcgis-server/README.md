# mcp-arcgis-server

This package exposes ArcGIS operations as MCP tools so other services or clients can search content, query layers, geocode locations, and run spatial workflows through a consistent interface.

## Core Capabilities

- feature querying and counting
- content and layer discovery
- geocoding and reverse geocoding
- proximity, buffer, and spatial workflows
- in-process or HTTP/SSE deployment modes

## Run It

Library mode:

```bash
pip install .
```

Standalone server mode:

```bash
pip install ".[http]"
mcp-arcgis-server
```

## Configuration

| Variable | Description |
|---|---|
| `ARCGIS_PORTAL_URL` | ArcGIS portal base URL |
| `ARCGIS_USERNAME` | Optional authenticated username |
| `ARCGIS_PASSWORD` | Optional authenticated password |
| `ARCGIS_VERIFY_SSL` | SSL verification toggle |
| `ARCGIS_TOKEN_URL` | Optional explicit token endpoint |
| `ARCGIS_SERVER_URL` | Optional server base URL for federated setups |
| `ARCGIS_MCP_HOST` | Bind host for standalone mode |
| `ARCGIS_MCP_PORT` | Bind port for standalone mode |
| `LOG_LEVEL` | Application log level |

## Notes

- The server supports both authenticated and anonymous access patterns depending on the ArcGIS resources you connect to.
- The public repository keeps examples generic and does not include organization-specific services, layers, or credentials.
