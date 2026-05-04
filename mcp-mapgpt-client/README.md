# mcp-client

Unified MCP host/client and REST API service. Connects to `mcp-arcgis-server` via MCP/SSE, runs LLM sampling via Azure OpenAI, orchestrates the query pipeline, and exposes the public REST surface.

## Architecture

```
User -> POST /api/v1/query     (plan only)
User -> POST /api/v1/execute   (plan + ArcGIS execution -> raw data)
User -> POST /api/v1/summarize (plan + execute + LLM summary)
User -> POST /api/v1/locate    (direct geocode/reverse-geocode)
User -> POST /api/v1/summarize-stat (plan + summarize_field -> LLM summary)
User -> GET  /api/v1/commands   (slash command discovery)
         |
   Orchestrator
    |-- RAG retrieval (core/rag/) -> pgvector
    |-- LLM call (core/llm_service.py) -> Azure OpenAI
    \-- MCP tool loop (core/mcp_client.py) -> mcp-arcgis-server -> ArcGIS REST
         |
   JSON response <- User
```

### Slash-Command Prefix Routing

The `/execute` endpoint supports slash-command prefixes that bypass LLM planning:
- `/locate <address or lat,lon>` -> routes to `locate()` (geocode/reverse-geocode)
- `/summarize <query>` -> routes to `summarize()` (execute + LLM summary)
- `/summarize-stat <query>` -> routes to `summarize_stat()` (field statistics + LLM summary)

Queries without a prefix run through the default plan -> execute pipeline.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (200 ok / 503 degraded) |
| `POST` | `/api/v1/query` | Generate a query plan via RAG + LLM (no execution) |
| `POST` | `/api/v1/execute` | Execute a query and return raw ArcGIS data |
| `POST` | `/api/v1/summarize` | Execute a query and return an LLM-generated summary |
| `POST` | `/api/v1/locate` | Geocode an address or reverse-geocode coordinates (no LLM) |
| `POST` | `/api/v1/summarize-stat` | Compute field statistics and return an LLM summary |
| `GET` | `/api/v1/commands` | List available slash commands |
| `POST` | `/api/v1/ingest` | Ingest a document into RAG |
| `GET` | `/docs` | Swagger UI (interactive API docs) |
| `GET` | `/redoc` | ReDoc (alternative API docs) |
| `GET` | `/openapi.json` | OpenAPI 3.x schema (JSON) |

## Internal Structure

```
mcp-mapgpt-client/
|-- main.py              # FastAPI app, lifespan, middleware
|-- api/
|   |-- routes.py        # REST endpoint handlers
|   \-- schemas.py       # Pydantic models
|-- core/
|   |-- orchestrator.py  # End-to-end pipeline
|   |-- llm_service.py   # Azure OpenAI (direct SDK)
|   |-- mcp_client.py    # MCP SSE client
|   \-- rag/
|       |-- database.py  # Async session factory
|       |-- embeddings.py # Embedding service
|       |-- vector_store.py # pgvector search
|       \-- models.py    # SQLAlchemy models
|-- prompts/             # Prompt templates
|-- tasks/               # Celery async jobs
\-- tests/               # Unit + integration tests
```

## Dependencies

Key dependencies:
- `mcp[cli]>=1.8.0` -- MCP client for tool calls to `mcp-arcgis-server`
- `openai>=1.0.0` -- Azure OpenAI direct SDK for LLM sampling
- `fastapi>=0.110.0` -- REST API framework
- `sqlalchemy[asyncio]>=2.0.0` + `pgvector>=0.3.0` -- RAG vector store

## Setup

```bash
pip install -r requirements.txt
cp ../.env.example ../.env  # Edit with credentials
```

## Running

```bash
uvicorn main:app --host 0.0.0.0 --port 8002
```

Or via Docker Compose:

```bash
docker-compose up mcp-mapgpt-client
```

## Environment Variables

See [../.env.example](../.env.example) for the full list.
