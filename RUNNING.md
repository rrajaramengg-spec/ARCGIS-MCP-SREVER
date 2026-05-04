# Running MCP ArcGIS Server

## Prerequisites

- Docker & Docker Compose
- `.env` file configured (copy from `.env.example`)

## Production (Core Services)

```powershell
docker-compose up -d
```

Starts:
- **mcp-arcgis-server** — MCP tool server for ArcGIS (in-process by default)
- **mcp-mapgpt-client** (`:8002`) — REST API + MCP host + RAG
- PostgreSQL, Redis, Celery worker

## With Demo Web UI

```powershell
docker-compose --profile demo up -d
```

Adds **webchat-ui** (`:8080`) — demo chat interface.

## Endpoints

| Service | URL |
|---|---|
| API | `http://localhost:8002/api/v1/execute` |
| Health | `http://localhost:8002/health` |
| Demo UI | `http://localhost:8080` (demo profile only) |

## Database Migrations

```powershell
docker-compose exec mcp-mapgpt-client alembic upgrade head
```

## Logs

```powershell
docker-compose logs -f mcp-mapgpt-client
```

## Rebuild

```powershell
docker-compose up -d --build
```
