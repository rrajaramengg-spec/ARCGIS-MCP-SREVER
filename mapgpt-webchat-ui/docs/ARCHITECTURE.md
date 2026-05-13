# Architecture

This document keeps the implementation-specific details for the demo UI so the root repository README can stay purpose-first.

## Implementation Snapshot

| Area | Choice |
|---|---|
| UI framework | React + TypeScript |
| Build tooling | Vite |
| Styling | Tailwind CSS |
| State | Zustand |
| Mapping | ArcGIS JavaScript SDK loaded from CDN |
| Test stack | Vitest, Testing Library, Playwright |
| Local serving | FastAPI wrapper for WebSocket relay and static assets |

## Component Tree

```
App (ErrorBoundary)
└── BrowserRouter
    └── Routes
        └── AppContent
            └── AppShell
                ├── Header
                │   └── Status dot, title, connection text, DEMO tag, session ID
                └── PanelLayout (mode: default | chat-max | map-max)
                    ├── ChatPanel
                    │   ├── MessageList
                    │   │   ├── MessageBubble (user)
                    │   │   ├── AssistantMessage
                    │   │   │   ├── MessageBubble (assistant)
                    │   │   │   ├── ReactMarkdown
                    │   │   │   ├── FeatureSummary (Badge[])
                    │   │   │   ├── FeatureTable
                    │   │   │   ├── FeedbackButtons
                    │   │   │   └── RawResponseModal
                    │   │   └── MessageBubble (error | system)
                    │   ├── ThinkingIndicator
                    │   ├── ProgressStep
                    │   ├── CommandDropdown
                    │   ├── ChatInput
                    │   └── LogsPanel
                    └── MapPanel (forwardRef → MapViewRef)
                        ├── MapViewComponent
                        │   ├── useMapView (lifecycle)
                        │   └── useGraphicsLayers (layers)
                        └── LocationPicker
```

## State Management

### Zustand Stores

| Store | Purpose | Key State |
|-------|---------|-----------|
| `useWebSocketStore` | Connection lifecycle | `isConnected`, `sessionId`, `send()`, `connect()` |
| `useChatStore` | Messages & UI | `messages[]`, `logs[]`, `isThinking`, `progressStep`, `inputText`, `isSendDisabled` |

Map state is **not** in Zustand — it's managed imperatively via `MapViewRef` (using `useImperativeHandle`) because ArcGIS objects are mutable class instances.

### Data Flow

```
User types query
  → ChatInput.onSend()
  → useWebSocketStore.send({ message, session_id })
  → WebSocket → FastAPI relay → mcp-mapgpt-client → LLM + MCP tools
  → WebSocket response
  → createMessageHandler() dispatches to useChatStore
  → MessageList re-renders with new AssistantMessage
  → onShowOnMap callback → MapViewRef.addQueryLayer() → ArcGIS map updates
```

### Message Types (WebSocket)

| Type | Direction | Shape |
|------|-----------|-------|
| `response` | server→client | `{ type: "response", data: ExecuteResponse }` |
| `progress` | server→client | `{ type: "progress", data: { step: string } }` |
| `error` | server→client | `{ type: "error", data: { error: string } }` |
| `log` | server→client | `{ type: "log", level: string, message: string }` |

## Key Design Decisions

1. **ArcGIS via CDN** — Not `@arcgis/core` npm package. The CDN approach avoids 50MB+ of WASM/worker bundling. Types are thin declarations in `src/types/arcgis.d.ts`.

2. **Imperative map ref** — ArcGIS MapView/GraphicsLayer are mutable objects. Using `forwardRef` + `useImperativeHandle` exposes `addQueryLayer()`, `addLocatePin()`, `clearAllLayers()` etc. as methods on the ref.

3. **No React Router pages** — Single-page app with one route (`/`). React Router is included for future extensibility.

4. **Normalize layer** — `normalizeQueryResponse()` converts diverse ArcGIS response shapes into a uniform `NormalizedResponse` with `LayerGroup[]` for consistent rendering.

## Development Surface

Primary folders:

- `src/components/` for shared UI primitives
- `src/features/chat/` for message flow and command UX
- `src/features/map/` for map lifecycle and rendering
- `src/services/` for API and WebSocket transport
- `src/stores/` for UI and connection state

Common scripts:

| Script | Purpose |
|---|---|
| `npm run dev` | Local development server |
| `npm run build` | Type-check and production build |
| `npm run test` | Unit tests |
| `npm run test:e2e` | End-to-end tests |
