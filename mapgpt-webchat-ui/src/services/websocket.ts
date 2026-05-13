/** WebSocket client service — ported from static/js/api.js */

import { WS_PATH } from "@/features/map/utils/constants";
import type { WsMessage, WsSendPayload } from "@/types/api";

export type MessageHandler = (msg: WsMessage) => void;
export type StatusHandler = (state: "connected" | "disconnected" | "error") => void;
export type LogHandler = (level: string, text: string) => void;

export class WebSocketService {
    private ws: WebSocket | null = null;
    private _sessionId: string | null = null;
    private messageHandler: MessageHandler | null = null;
    private statusHandler: StatusHandler | null = null;
    private logHandler: LogHandler | null = null;
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    get sessionId(): string | null {
        return this._sessionId;
    }

    get isConnected(): boolean {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }

    onMessage(handler: MessageHandler): void {
        this.messageHandler = handler;
    }

    onStatus(handler: StatusHandler): void {
        this.statusHandler = handler;
    }

    onLog(handler: LogHandler): void {
        this.logHandler = handler;
    }

    connect(): void {
        this._sessionId = crypto.randomUUID();
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        this.ws = new WebSocket(`${protocol}//${location.host}${WS_PATH}`);
        this.log("info", "Connecting to WebSocket...");

        this.ws.onopen = () => {
            this.statusHandler?.("connected");
            this.log("info", "WebSocket connected");
        };

        this.ws.onmessage = (event: MessageEvent) => {
            let msg: WsMessage;
            try {
                msg = JSON.parse(event.data as string) as WsMessage;
            } catch (err) {
                this.log("error", `Malformed JSON from server: ${(err as Error).message}`);
                this.messageHandler?.({
                    type: "error",
                    data: { error: "Received malformed response from server" },
                });
                return;
            }
            this.log("recv", `Response: ${JSON.stringify(msg).substring(0, 200)}...`);
            this.messageHandler?.(msg);
        };

        this.ws.onclose = () => {
            this.statusHandler?.("disconnected");
            this.log("warn", "WebSocket disconnected, reconnecting in 3s...");
            this.reconnectTimer = setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = () => {
            this.statusHandler?.("error");
            this.log("error", "WebSocket error");
        };
    }

    send(text: string): boolean {
        if (this.ws && this.ws.readyState === WebSocket.OPEN && this._sessionId) {
            const payload: WsSendPayload = {
                message: text,
                session_id: this._sessionId,
            };
            this.ws.send(JSON.stringify(payload));
            this.log("sent", `Query: ${text}`);
            return true;
        }
        return false;
    }

    disconnect(): void {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.onclose = null; // Prevent reconnect on intentional close
            this.ws.close();
            this.ws = null;
        }
    }

    private log(level: string, text: string): void {
        this.logHandler?.(level, text);
    }
}
