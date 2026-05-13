import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { createMessageHandler } from "@/features/chat/handleResponse";
import { AppShell } from "@/features/layout/AppShell";
import { MapPanel, type MapPanelRef } from "@/features/map/MapPanel";
import { useChatStore } from "@/stores/chat";
import { onWebSocketLog, useWebSocketStore } from "@/stores/websocket";
import type { ExecuteResponse } from "@/types/api";
import { normalizeQueryResponse } from "@/utils/normalize";
import { useCallback, useEffect, useRef } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

function AppContent() {
    const mapRef = useRef<MapPanelRef>(null);

    // Set up WebSocket connection + message handler on mount
    useEffect(() => {
        const { connect, setMessageHandler } = useWebSocketStore.getState();

        const handler = createMessageHandler({
            onShowOnMap: (rawData) => {
                if (!mapRef.current) return;
                const data = rawData as ExecuteResponse;
                const normalized = normalizeQueryResponse(data);
                if (normalized && normalized.layers.some((l) => l.features?.length)) {
                    mapRef.current.addQueryLayer(
                        data,
                        data.message || "",
                        data.query_id || `auto-${Date.now()}`,
                    );
                }
            },
            onZoomToLocate: (x, y) => {
                mapRef.current?.addLocatePin(x, y);
            },
        });

        setMessageHandler(handler);
        connect();

        // Wire log handler
        onWebSocketLog((level, text) => {
            useChatStore.getState().addLog(level as "info" | "warn" | "error" | "sent" | "recv", text);
        });
    }, []);

    const handleZoomToQuery = useCallback((queryId: string) => {
        mapRef.current?.zoomToQuery(queryId);
    }, []);

    const handleZoomToLocate = useCallback((x: number, y: number) => {
        mapRef.current?.addLocatePin(x, y);
    }, []);

    return (
        <AppShell
            chatPanel={
                <ChatPanel
                    onZoomToQuery={handleZoomToQuery}
                    onZoomToLocate={handleZoomToLocate}
                />
            }
            mapPanel={<MapPanel ref={mapRef} />}
        />
    );
}

export default function App() {
    return (
        <ErrorBoundary>
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<AppContent />} />
                </Routes>
            </BrowserRouter>
        </ErrorBoundary>
    );
}
