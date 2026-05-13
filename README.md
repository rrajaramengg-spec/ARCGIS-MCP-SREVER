# MapGPT

MapGPT is an open geospatial assistant project that turns plain-language questions into ArcGIS-ready queries, map lookups, and summarized results.

The repository is organized so the core pieces can be used independently:

| Component | Purpose |
|---|---|
| `mcp-arcgis-server/` | MCP tool server for ArcGIS search, query, geocoding, and spatial operations |
| `mcp-mapgpt-client/` | API layer that orchestrates prompts, retrieval, and tool execution |
| `mapgpt-webchat-ui/` | Demo web interface for trying the workflow end to end |

## What This Repository Is For

This project is intended as a reusable reference for teams building natural-language experiences on top of ArcGIS data. It focuses on three practical outcomes:

- turning a user request into a valid GIS action
- keeping tool execution inspectable instead of opaque
- offering a demo interface without coupling the whole system to one UI

## Quick Start

```powershell
Copy-Item .env.example .env
# Fill in your own credentials and endpoints in .env

docker-compose up -d
```

To run the demo UI as well:

```powershell
docker-compose --profile demo up -d
```

Default local endpoints:

- API health: `http://localhost:8002/health`
- API docs: `http://localhost:8002/docs`
- Demo UI: `http://localhost:8080`

## Public Documentation

The public docs in this repository stay focused on usage and system boundaries.

- Root setup and publication-safe configuration live here in this README.
- Component-specific docs live in each package directory.
- UI implementation notes and stack details live in `mapgpt-webchat-ui/docs/ARCHITECTURE.md`.

## Repository Layout

```text
.
├── mcp-arcgis-server/
├── mcp-mapgpt-client/
├── mapgpt-webchat-ui/
├── alembic/
├── docker-compose.yml
└── .env.example
```

## Configuration

The project uses environment variables for credentials and deployment-specific values. The checked-in examples only contain placeholders.

Minimum values you will usually need:

- ArcGIS portal URL or service access details
- an LLM endpoint and key
- a database connection for retrieval features
- a Redis instance for caching and background work

See `.env.example` for the complete placeholder list.

## Notes For Public Use

- No production credentials or organization-specific values should be committed.
- The demo UI is optional and should be treated as a sample client, not a required production surface.
- Database migrations and internal retrieval structures are included for local development, but the public README intentionally avoids prescribing a specific private data model.

## Contributing

Contributions are welcome if they improve portability, clarity, or the core geospatial workflow. If you are publishing a derived version, review your own environment files, sample prompts, and deployment defaults before release.

## License

See `LICENSE`.
