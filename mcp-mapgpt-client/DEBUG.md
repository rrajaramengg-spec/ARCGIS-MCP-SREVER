# Debugging Guide — mcp-client

## Key Breakpoint Locations

### Locate Flow
- `core/orchestrator.py` -> `_execute_locate()` — LLM plan routes to geocode/reverse_geocode
- `core/orchestrator.py` -> `locate()` — Direct geocoding without LLM planning
- `api/routes.py` -> `locate()` — REST endpoint handler

### Summarize-Stat Flow
- `core/orchestrator.py` -> `summarize_stat()` — A/D hybrid field identification + summarize_field MCP tool
- Look for `A-phase heuristic` and `D-phase fallback` log messages in the output

### Prefix Routing
- `core/orchestrator.py` -> `execute()` — Search for `prefix_routes` to see the slash-command prefix matching logic
- Prefixes must end with a space to match (e.g., `/locate ` not `/locate`)

### Command Discovery
- `api/routes.py` -> `COMMANDS` list — Static command registry
- `api/routes.py` -> `list_commands()` — GET endpoint

## Useful Log Searches

```
# Locate action routing
grep "Prefix routing:" logs/mcp-client.log

# A/D hybrid field detection
grep "A-phase heuristic\|D-phase" logs/mcp-client.log

# MCP tool calls
grep "Calling MCP tool\|Calling summarize_field\|Direct locate" logs/mcp-client.log
```
