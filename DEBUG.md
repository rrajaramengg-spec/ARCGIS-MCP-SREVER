# Debugging Guide

## VS Code Launch Configurations

### Standalone MCP Server

Debug `mcp-arcgis-server` as a standalone HTTP/SSE server:

```json
{
    "name": "MCP ArcGIS Server",
    "type": "debugpy",
    "request": "launch",
    "module": "mcp_arcgis_server",
    "cwd": "${workspaceFolder}/mcp-arcgis-server",
    "envFile": "${workspaceFolder}/.env",
    "env": {
        "ARCGIS_MCP_HOST": "0.0.0.0",
        "ARCGIS_MCP_PORT": "8001",
        "LOG_LEVEL": "DEBUG"
    }
}
```

### Pytest

Run tests with debugger attached:

```json
{
    "name": "Pytest: MCP ArcGIS Server",
    "type": "debugpy",
    "request": "launch",
    "module": "pytest",
    "args": ["tests/", "-v", "--tb=short"],
    "cwd": "${workspaceFolder}/mcp-arcgis-server",
    "envFile": "${workspaceFolder}/.env"
}
```

### Attach to Docker

Attach debugger to the running backend container:

```json
{
    "name": "Attach: Docker Backend",
    "type": "debugpy",
    "request": "attach",
    "connect": {
        "host": "localhost",
        "port": 5678
    },
    "pathMappings": [
        {
            "localRoot": "${workspaceFolder}",
            "remoteRoot": "/app"
        }
    ]
}
```

## Breakpoint Placement

### Tool Functions

```
mcp_arcgis_server/tools/query.py       -> _query_features()
mcp_arcgis_server/tools/spatial.py     -> _spatial_join_query()
mcp_arcgis_server/tools/discovery.py   -> _search_content(), _search_layers()
mcp_arcgis_server/tools/analysis.py    -> _summarize_field(), _get_feature_table()
mcp_arcgis_server/tools/buffer.py      -> _buffer_and_query()
mcp_arcgis_server/tools/proximity.py   -> _find_nearby()
mcp_arcgis_server/tools/geocoding.py   -> _geocode(), _reverse_geocode()
```

### Client Layer

```
mcp_arcgis_server/arcgis/client.py     -> query_layer(), buffer_geometry(), geocode()
mcp_arcgis_server/arcgis/auth.py       -> GISAuthManager.initialize()
```

### In-Process Transport

```
mcp_arcgis_server/transport/memory.py  -> connect_in_process()
mcp_arcgis_server/server.py            -> create_server()
```

## Environment Setup

Create a `.env` file at the project root:

```bash
ARCGIS_PORTAL_URL=https://your-portal.example.com/arcgis
ARCGIS_USERNAME=your-username
ARCGIS_PASSWORD=your-password
```
