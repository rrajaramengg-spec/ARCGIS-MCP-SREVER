# mcp-mapgpt-client

This service is the API-facing orchestrator for MapGPT. It accepts user requests, decides which workflow to run, calls the MCP ArcGIS server when needed, and returns either raw geospatial results or summarized responses.

## Public API Surface

The service exposes a small set of practical endpoints:

- `GET /health`
- `POST /api/mapgpt/v1/query`
- `POST /api/mapgpt/v1/execute`
- `POST /api/mapgpt/v1/summarize`
- `POST /api/mapgpt/v1/locate`
- `POST /api/mapgpt/v1/summarize-stat`
- `GET /api/mapgpt/v1/commands`
- `POST /api/mapgpt/v1/ingest`

Interactive docs are available locally at `/docs` when the service is running.

## Run It

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8002
```

Or through Docker Compose:

```bash
docker-compose up mcp-mapgpt-client
```

## Configuration

Use the repository `.env.example` as a placeholder-only template for your own environment values.

## Notes

- This public README stays at the service boundary and avoids publishing private retrieval schema details.
- The repository source still contains the implementation required to run the project locally, but organization-specific prompts, datasets, and credentials are intentionally not included.
