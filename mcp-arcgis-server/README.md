# mcp-arcgis-server

MCP server exposing ArcGIS REST API operations as typed MCP tools. Usable as a standalone HTTP/SSE server or as an in-process library with zero network overhead.

## Overview

| Tool | Module | Description |
|---|---|---|
| `query_features` | query | Query features from a layer with WHERE clause, field selection, and optional spatial filter |
| `count_features` | query | Count features matching a WHERE clause without returning data |
| `spatial_join_query` | spatial | Query boundary geometry, then filter a target layer spatially |
| `join_layers` | spatial | Client-side attribute join of two layers on a shared field |
| `execute_query_plan` | plan | Execute a full multi-step query plan in a single call |
| `search_content` | discovery | Search ArcGIS portal for content items by keyword and type |
| `search_layers` | discovery | Discover feature layers on a server or portal |
| `summarize_field` | analysis | Compute field statistics or unique values for a feature layer field |
| `get_feature_table` | analysis | Retrieve a formatted feature table (JSON or markdown) |
| `buffer_and_query` | buffer | Create a buffer zone and optionally find features within it |
| `find_nearby` | proximity | Find features near a location, sorted by distance |
| `geocode` | geocoding | Geocode an address to geographic coordinates |
| `reverse_geocode` | geocoding | Reverse geocode coordinates to an address |

**13 tools** across 8 modules.

## Quick Start

### As a library (in-process)

```bash
pip install .
```

```python
from mcp_arcgis_server import create_server, connect_in_process

mcp, client, auth = create_server()
await auth.initialize()

async with connect_in_process(mcp) as session:
    tools = await session.list_tools()  # 13 tools
    result = await session.call_tool("query_features", {
        "layer_url": "https://services.arcgis.com/public/FeatureServer/0",
        "where": "1=1"
    })
```

### As a standalone HTTP/SSE server

```bash
pip install ".[http]"
mcp-arcgis-server
# or: python -m mcp_arcgis_server
```

## Tool Reference

### query_features

Query features from an ArcGIS feature layer.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `layer_url` | string | required | Full URL to the ArcGIS feature layer endpoint |
| `where` | string | `"1=1"` | SQL WHERE clause to filter features |
| `out_fields` | string | `"*"` | Comma-separated list of fields to return |
| `return_geometry` | bool | `true` | Whether to include geometry |
| `geometry_filter` | string | `null` | JSON geometry string for spatial filtering |
| `spatial_rel` | string | `"esriSpatialRelIntersects"` | Spatial relationship type |

### count_features

Count features matching a WHERE clause.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `layer_url` | string | required | Full URL to the feature layer |
| `where` | string | `"1=1"` | SQL WHERE clause |

Returns: `{"count": <integer>}`

### spatial_join_query

Query boundary geometry, then filter a target layer spatially.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `boundary_layer_url` | string | required | URL of the boundary layer |
| `boundary_where` | string | required | WHERE clause to select boundary feature(s) |
| `target_layer_url` | string | required | URL of the target layer |
| `operation` | string | `"where"` | `"where"` for features, `"count"` for count only |

### join_layers

Client-side attribute join of two layers on a shared field.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `primary_layer_url` | string | required | URL of the primary layer |
| `primary_where` | string | `"1=1"` | WHERE clause for primary layer |
| `primary_fields` | string | `"*"` | Fields from primary layer |
| `secondary_layer_url` | string | required | URL of the secondary layer |
| `secondary_where` | string | `"1=1"` | WHERE clause for secondary layer |
| `secondary_fields` | string | `"*"` | Fields from secondary layer |
| `join_field` | string | required | Attribute field name to join on |

### execute_query_plan

Execute a full multi-step query plan (single-layer queries, counts, spatial joins).

| Parameter | Type | Description |
|---|---|---|
| `query_plan` | string | JSON string of the query plan |

### search_content

Search ArcGIS portal/server for content items by keyword and type.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Search keyword(s) for portal content |
| `item_type` | string | `null` | Filter by item type (e.g. `"Feature Layer"`, `"Map Service"`) |
| `max_items` | int | `10` | Maximum results to return (max 50) |

Returns: `{"items": [...], "count": <int>, "query": "..."}`

### search_layers

Discover available feature layers on an ArcGIS Server or portal.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `service_url` | string | `null` | ArcGIS Server REST endpoint URL |
| `query` | string | `null` | Keyword to search portal for feature layers |

At least one parameter must be provided.

### summarize_field

Compute field statistics or unique values for a feature layer field.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `layer_url` | string | required | Full URL to the feature layer |
| `field_name` | string | required | Name of the field to summarize |
| `where` | string | `"1=1"` | SQL WHERE clause to filter before summarization |
| `statistics` | string | `null` | Comma-separated stats: `count,min,max,avg,stddev` |

- Numeric fields: returns count, min, max, avg, stddev, null_count
- String fields: returns unique values with counts, sorted by frequency

### get_feature_table

Retrieve a formatted feature table from a feature layer.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `layer_url` | string | required | Full URL to the feature layer |
| `where` | string | `"1=1"` | SQL WHERE clause |
| `fields` | string | `"*"` | Comma-separated field list |
| `max_records` | int | `50` | Maximum records (max 200) |
| `format` | string | `"json"` | Output format: `"json"` or `"markdown"` |

### buffer_and_query

Create a buffer zone around a geometry and optionally find features within it.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `geometry` | string | required | Input geometry as JSON (ArcGIS JSON or GeoJSON) |
| `radius` | float | required | Buffer distance |
| `unit` | string | `"feet"` | Distance unit: feet, meters, kilometers, miles |
| `layer_url` | string | `null` | Feature layer to query within the buffer |
| `where` | string | `"1=1"` | SQL WHERE clause for query |
| `out_fields` | string | `"*"` | Fields to return |

### find_nearby

Find features near a location, sorted by distance.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `layer_url` | string | required | Feature layer to search |
| `location` | string | required | Center point as JSON (ArcGIS JSON or GeoJSON) |
| `radius` | float | required | Search radius |
| `unit` | string | `"miles"` | Distance unit: feet, meters, kilometers, miles |
| `where` | string | `"1=1"` | SQL WHERE clause |
| `out_fields` | string | `"*"` | Fields to return |
| `max_results` | int | `20` | Maximum nearest features to return |

Returns features enriched with computed geodesic distance, sorted nearest-first.

### geocode

Geocode an address to geographic coordinates. Designed for prompt-routed invocation via `/locate-ag`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `address` | string | required | Address string to geocode |
| `max_results` | int | `1` | Maximum candidates (max 10) |
| `out_sr` | int | `4326` | Output spatial reference WKID |

### reverse_geocode

Reverse geocode coordinates to an address. Designed for prompt-routed invocation via `/locate-ag`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `latitude` | float | required | Latitude in WGS84 (-90 to 90) |
| `longitude` | float | required | Longitude in WGS84 (-180 to 180) |
| `distance` | float | `100` | Search radius in meters |

## Authentication

Multi-strategy GIS initialization with automatic fallback:

1. **Standard auth** — `GIS(url, username, password)`
2. **Explicit token URL** — `GIS(url, username, password, token_url=..., use_gen_token=True)`
3. **Pre-generated REST token** — Direct REST POST to generate token, then `GIS(url, token=...)`

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ARCGIS_PORTAL_URL` | Yes | ArcGIS portal base URL |
| `ARCGIS_USERNAME` | No | Portal username |
| `ARCGIS_PASSWORD` | No | Portal password |
| `ARCGIS_VERIFY_SSL` | No | SSL verification (default: `true`) |
| `ARCGIS_TOKEN_URL` | No | Explicit token endpoint URL |
| `ARCGIS_SERVER_URL` | No | ArcGIS Server base URL for token resolution |
| `ARCGIS_MCP_HOST` | No | HTTP server bind host (default: `0.0.0.0`) |
| `ARCGIS_MCP_PORT` | No | HTTP server bind port (default: `8001`) |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

Domain-based routing: if a layer URL's hostname matches `ARCGIS_PORTAL_URL`, the authenticated GIS instance is used. Otherwise, anonymous access is assumed.

## Transport Modes

### In-process (library mode)

Zero network overhead. Import `create_server` and `connect_in_process`:

```python
from mcp_arcgis_server import create_server, connect_in_process

mcp, client, auth = create_server()
await auth.initialize()
async with connect_in_process(mcp) as session:
    result = await session.call_tool("query_features", {...})
```

### HTTP/SSE (standalone server)

For external consumers or standalone deployment:

```bash
pip install ".[http]"
mcp-arcgis-server
```

Endpoints:
- `GET /health` — Health check (`{"status": "ok", "service": "mcp-arcgis-server"}`)
- `GET /sse` — MCP SSE transport endpoint

## Adding New Tools

1. Create `mcp_arcgis_server/tools/my_tool.py`:

```python
from mcp.server.fastmcp import FastMCP
from ..arcgis.client import ArcGISClient

async def _my_operation(client: ArcGISClient, ...) -> dict:
    """Core logic — testable without server."""
    ...

def register(mcp: FastMCP, client: ArcGISClient) -> None:
    @mcp.tool()
    async def my_operation(...) -> dict:
        return await _my_operation(client, ...)
```

2. Add one line to `mcp_arcgis_server/server.py`:

```python
from .tools import my_tool
my_tool.register(mcp, client)
```

## Architecture

```
mcp-arcgis-server/
├── mcp_arcgis_server/
│   ├── __init__.py          # Public API: create_server(), connect_in_process()
│   ├── server.py            # FastMCP server factory + tool registration
│   ├── main.py              # CLI entry point (HTTP/SSE)
│   ├── logging_config.py    # Logging setup
│   ├── tools/
│   │   ├── query.py         # query_features, count_features
│   │   ├── spatial.py       # spatial_join_query, join_layers
│   │   ├── plan.py          # execute_query_plan
│   │   ├── discovery.py     # search_content, search_layers
│   │   ├── analysis.py      # summarize_field, get_feature_table
│   │   ├── buffer.py        # buffer_and_query
│   │   ├── proximity.py     # find_nearby
│   │   └── geocoding.py     # geocode, reverse_geocode
│   ├── arcgis/
│   │   ├── auth.py          # GISAuthManager (multi-strategy auth)
│   │   ├── client.py        # ArcGISClient (thread pool, query execution)
│   │   └── geometry.py      # Geometry utilities, FeatureSet conversion
│   └── transport/
│       ├── http.py          # Starlette ASGI app (SSE + /health)
│       └── memory.py        # In-process anyio memory streams
├── pyproject.toml
├── main.py                  # Legacy entry point
├── tests/
└── README.md
```

All blocking `arcgis` SDK calls (`GIS()`, `FeatureLayer.query()`, `fl.properties`, `geocode()`, `buffer()`) are offloaded to a `ThreadPoolExecutor(max_workers=8)`. Token refresh is guarded by `asyncio.Lock` to prevent concurrent re-initialization races.

### Prompt Routing

The `geocode` and `reverse_geocode` tools are designed for **prompt-routed invocation** via the `/locate-ag` prompt. The LLM routes address/coordinate lookup requests to these tools through the `/locate-ag` prompt rather than direct tool selection.

## Development

```bash
pip install -e ".[dev,http]"
pytest tests/ -v
```

## Public API Reference

### `create_server() -> tuple[FastMCP, ArcGISClient, GISAuthManager]`

Create a configured FastMCP server with all tools registered. Returns the server, client, and auth manager for lifecycle management.

### `connect_in_process(server: FastMCP) -> AsyncContextManager[ClientSession]`

Async context manager that creates an MCP `ClientSession` connected to the server via anyio memory streams. Yields a ready-to-use session.
