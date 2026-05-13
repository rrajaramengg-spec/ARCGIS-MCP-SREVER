/** WebSocket Zustand store — connection lifecycle + message dispatch */

import { WebSocketService } from "@/services/websocket";
import type { WsMessage } from "@/types/api";
import { create } from "zustand";

export type MessageHandler = (msg: WsMessage) => void;

interface WebSocketState {
    isConnected: boolean;
    sessionId: string | null;
    /** External message handler — set by app shell to route messages to chat store / map */
    messageHandler: MessageHandler | null;
    /** Send a text message. Returns false if not connected. */
    send: (text: string) => boolean;
    /** Open the WebSocket connection. Call once on app mount. */
    connect: () => void;
    /** Close the WebSocket connection. Call on app unmount. */
    disconnect: () => void;
    /** Register the handler for incoming messages. */
    setMessageHandler: (handler: MessageHandler) => void;
}

const service = new WebSocketService();

export const useWebSocketStore = create<WebSocketState>((set, get) => {
    // Wire service callbacks to store updates
    service.onStatus((state) => {
        set({
            isConnected: state === "connected",
            sessionId: service.sessionId,
        });
    });

    service.onMessage((msg) => {
        const handler = get().messageHandler;
        handler?.(msg);
    });

    return {
        isConnected: false,
        sessionId: null,
        messageHandler: null,

        send: (text: string) => service.send(text),

        connect: () => {
            service.connect();
            set({ sessionId: service.sessionId });
        },

        disconnect: () => {
            service.disconnect();
            set({ isConnected: false, sessionId: null });
        },

        setMessageHandler: (handler: MessageHandler) => {
            set({ messageHandler: handler });
        },
    };
});

/** Expose log handler registration for the log panel. */
export function onWebSocketLog(handler: (level: string, text: string) => void): void {
    service.onLog(handler);
}
