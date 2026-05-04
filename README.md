# MCP ArcGIS Server

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![MCP](https://img.shields.io/badge/MCP-1.8+-purple.svg)](https://modelcontextprotocol.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)

A RAG-powered natural language interface for geospatial data, decomposed into MCP (Model Context Protocol) modules.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  mcp-client         │────▶│  mcp-arcgis-server   │────▶│ ArcGIS REST API │
│  (REST API + MCP    │in-  │  (Python package)    │HTTP │                 │
│   host + RAG)       │proc │  13 spatial tools     │     │                 │
│  :8002              │     │                      │     │                 │
└─────────────────────┘     └──────────────────────┘     └─────────────────┘
         ▲
         │ REST/WS
┌────────┴──────────┐    ┌─────────────────────┐
│ webchat-ui        │    │  Postgres + Redis   │
│ (Demo Only :8080) │    │  (Infrastructure)   │
└───────────────────┘    └─────────────────────┘
```

### Modules

| Module | Description | Port |
|---|---|---|
| [`mcp-arcgis-server/`](mcp-arcgis-server/) | Installable MCP server package with 13 ArcGIS tools (query, spatial, discovery, analysis, buffer, proximity, geocoding) | — |
| [`mcp-mapgpt-client/`](mcp-mapgpt-client/) | REST API + MCP host with RAG pipeline, locate/summarize-stat endpoints, and slash-command routing | 8002 |
| [`mapgpt-webchat-ui/`](mapgpt-webchat-ui/) | Demo web chat UI with slash-command suggestion dropdown (not production) | 8080 |

## Quick Start

```powershell
# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Start production services
docker-compose up -d

# (Optional) Start with demo web UI
docker-compose --profile demo up -d

# API is at http://localhost:8002/api/v1/
# Health: http://localhost:8002/health
```

## Configuration

Configure via environment variables in `.env`:

```env
# Application
APP_NAME=MCP ArcGIS Server
APP_VERSION=1.0.0
DEBUG=false

# Database
DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/gisdb

# Redis
REDIS_URL=redis://localhost:6379/0

# Azure OpenAI
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=your-endpoint

# ArcGIS
ARCGIS_PORTAL_URL=https://your-arcgis-portal.example.com/arcgis
ARCGIS_USERNAME=your-username
ARCGIS_PASSWORD=your-password
```

See [`.env.example`](./.env.example) for all configuration options.

## API Endpoints

### Query Processing
- `POST /api/v1/execute` — Process natural language query and return ArcGIS data
- `POST /api/v1/query` — Generate a query plan via RAG + LLM (no execution)
- `POST /api/v1/summarize` — Execute and return LLM-generated summary
- `POST /api/v1/locate` — Geocode/reverse-geocode (no LLM)
- `POST /api/v1/summarize-stat` — Field statistics with LLM summary
- `POST /api/v1/arcgis-execute` — Direct ArcGIS tool execution (no RAG)
- `GET /api/v1/commands` — Available slash commands

### Document Management
- `POST /api/v1/ingest` — Ingest documents into RAG vector store

## Technology Stack

- **Framework**: FastAPI (async)
- **Database**: PostgreSQL 16 + pgvector
- **Cache**: Redis 7
- **LLM**: Azure OpenAI / OpenAI
- **RAG**: LangChain + LangGraph
- **Task Queue**: Celery
- **ORM**: SQLAlchemy (async)
- **Migrations**: Alembic
- **MCP**: Model Context Protocol 1.8+

## Docker Deployment

### Services

- **postgres**: PostgreSQL 16 with pgvector
- **redis**: Redis 7 for caching
- **mcp-mapgpt-client**: REST API + MCP host
- **celery-worker**: Background task processor
- **webchat-ui**: Demo web chat (optional, `--profile demo`)

### Commands

```powershell
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f mcp-mapgpt-client

# Stop services
docker-compose down

# Rebuild
docker-compose up -d --build
```

## Database Migrations

```powershell
# Apply migrations
docker-compose exec mcp-mapgpt-client alembic upgrade head

# Create new migration
docker-compose exec mcp-mapgpt-client alembic revision --autogenerate -m "description"
```

## Development

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ with pgvector
- Redis 7+
- Azure OpenAI or OpenAI API Key
- ArcGIS Enterprise or ArcGIS Online account

### Local Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8002
```

### Running Tests

```powershell
pytest tests/ -v
```

## Features

- Natural language query processing via RAG + LLM
- 13 typed MCP tools for ArcGIS operations
- Vector similarity search with pgvector
- Spatial joins, buffer analysis, proximity search
- Geocoding and reverse geocoding
- Field-level statistics and summarization
- Slash-command prefix routing
- Async processing with Celery
- Docker deployment
- OpenAPI documentation (Swagger UI / ReDoc)

## License

[Your License Here]

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request
