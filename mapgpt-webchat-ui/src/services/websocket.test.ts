import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WebSocketService } from "./websocket";

// Mock WebSocket
class MockWebSocket {
    static readonly OPEN = 1;
    static readonly CLOSED = 3;
    readyState = MockWebSocket.OPEN;
    onopen: (() => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    sent: string[] = [];

    send(data: string) {
        this.sent.push(data);
    }

    close() {
        this.readyState = MockWebSocket.CLOSED;
    }
}

let mockWsInstance: MockWebSocket;

beforeEach(() => {
    mockWsInstance = new MockWebSocket();
    vi.stubGlobal("WebSocket", class extends MockWebSocket {
        constructor() {
            super();
            Object.assign(this, mockWsInstance);
            // eslint-disable-next-line @typescript-eslint/no-this-alias
            mockWsInstance = this;
        }
    });
    vi.stubGlobal("location", { protocol: "http:", host: "localhost:8080" });
    vi.stubGlobal("crypto", { randomUUID: () => "test-uuid-1234" });
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("WebSocketService", () => {
    it("generates a session ID on connect", () => {
        const svc = new WebSocketService();
        svc.connect();
        expect(svc.sessionId).toBe("test-uuid-1234");
    });

    it("reports connected status on open", () => {
        const svc = new WebSocketService();
        const statusFn = vi.fn();
        svc.onStatus(statusFn);
        svc.connect();
        mockWsInstance.onopen?.();
        expect(statusFn).toHaveBeenCalledWith("connected");
    });

    it("sends JSON payload with session_id", () => {
        const svc = new WebSocketService();
        svc.connect();
        const sent = svc.send("hello");
        expect(sent).toBe(true);
        expect(mockWsInstance.sent).toHaveLength(1);
        const payload = JSON.parse(mockWsInstance.sent[0]);
        expect(payload).toEqual({
            message: "hello",
            session_id: "test-uuid-1234",
        });
    });

    it("returns false when not connected", () => {
        const svc = new WebSocketService();
        expect(svc.send("hello")).toBe(false);
    });

    it("calls message handler on incoming message", () => {
        const svc = new WebSocketService();
        const msgFn = vi.fn();
        svc.onMessage(msgFn);
        svc.connect();
        const msg = { type: "response", data: { action: "query", message: "ok" } };
        mockWsInstance.onmessage?.({ data: JSON.stringify(msg) });
        expect(msgFn).toHaveBeenCalledWith(msg);
    });

    it("handles malformed JSON gracefully", () => {
        const svc = new WebSocketService();
        const msgFn = vi.fn();
        svc.onMessage(msgFn);
        svc.connect();
        mockWsInstance.onmessage?.({ data: "not-json{" });
        expect(msgFn).toHaveBeenCalledWith(
            expect.objectContaining({ type: "error" }),
        );
    });

    it("disconnects cleanly", () => {
        const svc = new WebSocketService();
        svc.connect();
        svc.disconnect();
        expect(svc.isConnected).toBe(false);
    });
});
