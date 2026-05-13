/** handleResponse — routes incoming WebSocket messages to chat store + map actions. */

import { useChatStore } from "@/stores/chat";
import type { WsMessage } from "@/types/api";

interface MapCallbacks {
    onZoomToQuery?: (queryId: string, rawData: unknown) => void;
    onZoomToLocate?: (x: number, y: number) => void;
    onShowOnMap?: (rawData: unknown) => void;
}

/**
 * Creates a message handler for incoming WebSocket messages.
 * Dispatches to chat store and optionally triggers map actions.
 */
export function createMessageHandler(mapCallbacks?: MapCallbacks) {
    return (msg: WsMessage) => {
        const store = useChatStore.getState();

        if (msg.type === "progress") {
            store.setProgressStep(msg.data?.step || null);
            return;
        }

        if (msg.type === "error") {
            store.addErrorMessage(msg.data?.error || "Unknown error");
            store.setSendDisabled(false);
            return;
        }

        if (msg.type === "response") {
            const data = msg.data;
            const action = data?.action;
            const text = data?.message || "Done";
            const queryId = data?.query_id || null;

            store.addAssistantMessage(text, data ?? null, queryId);
            store.setSendDisabled(false);

            // Auto-show on map for query/analyze actions with results
            if (
                mapCallbacks?.onShowOnMap &&
                data &&
                (action === "query" || action === "analyze") &&
                (data.results?.length || data.data)
            ) {
                mapCallbacks.onShowOnMap(data);
            }

            // Auto-zoom for locate actions
            if (action === "locate" && data && mapCallbacks?.onZoomToLocate) {
                let loc: { x: number; y: number } | null = null;
                if (Array.isArray(data.results)) {
                    const geo = data.results.find((r) => r.type === "geocode");
                    if (geo && "location" in geo) {
                        loc = geo.location as { x: number; y: number };
                    }
                }
                if (loc?.x != null && loc?.y != null) {
                    mapCallbacks.onZoomToLocate(loc.x, loc.y);
                }
            }
        }
    };
}
