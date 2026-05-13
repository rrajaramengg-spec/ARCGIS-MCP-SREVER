import { useWebSocketStore } from "@/stores/websocket";

export function Header() {
    const isConnected = useWebSocketStore((s) => s.isConnected);
    const sessionId = useWebSocketStore((s) => s.sessionId);

    return (
        <div className="flex items-center gap-3 px-4 py-2 bg-surface shadow-md">
            <div
                className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-success animate-pulse" : "bg-error-fg"}`}
                aria-label={isConnected ? "Connected" : "Disconnected"}
            />
            <h1 className="text-base font-semibold text-text m-0">MapGPT Chat</h1>
            <span className="text-sm text-muted">
                {isConnected ? "Connected" : "Disconnected — reconnecting..."}
            </span>
            <span className="text-[10px] bg-accent-soft text-accent px-1.5 py-0.5 rounded font-semibold uppercase tracking-wide">
                DEMO
            </span>
            {sessionId && (
                <span className="text-[10px] text-muted ml-auto font-mono">
                    {sessionId.slice(0, 8)}
                </span>
            )}
        </div>
    );
}
