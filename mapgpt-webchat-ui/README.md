# webchat-ui

**Demo / Development Only** — A lightweight browser-based chat interface for testing the GIS query API. NOT for production use.

## Features

- WebSocket chat relay to the MCP client REST API
- `/` keystroke shows available slash commands with filtered dropdown
- `@` keystroke shows available MCP resources
- Slash-command prefix routing (e.g., `/locate Seattle, WA`) handled by backend
- Command suggestions cached after first fetch
- Conversation history maintained per browser session

## Running

```bash
pip install -r requirements.txt
uvicorn web_app:app --host 0.0.0.0 --port 8080
```

Or via Docker Compose:

```bash
docker-compose --profile demo up webchat-ui
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GIS_CLIENT_URL` | `http://mcp-mapgpt-client:8002` | URL of the MCP client service |
| `LOG_LEVEL` | `INFO` | Logging level |

## Note

This service is included in Docker Compose under `profiles: [demo]` and is excluded from default production deployments.
