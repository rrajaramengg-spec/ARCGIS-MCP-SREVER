# mapgpt-webchat-ui

This package is the optional demo interface for MapGPT. It provides a browser-based chat and map experience for local evaluation, demos, and UI experimentation.

It is not required to run the API stack, and it should be treated as a sample client rather than a production deployment target.

## What It Includes

- a chat surface for natural-language requests
- an ArcGIS-backed map panel for locate and query results
- command shortcuts for common actions
- local build and test tooling for UI changes

## Run It

```bash
npm install
npm run dev
```

Or through Docker Compose:

```bash
docker-compose --profile demo up -d --build mapgpt-webchat-ui
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MAPGPT_CLIENT_URL` | `http://mcp-mapgpt-client:8002` | Base URL for the API service |
| `LOG_LEVEL` | `INFO` | Application log level |

## Additional Notes

- Detailed implementation notes live in `docs/ARCHITECTURE.md`.
- The demo UI is excluded from the default Docker Compose profile.
