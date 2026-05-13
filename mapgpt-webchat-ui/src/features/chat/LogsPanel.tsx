import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { useChatStore } from "@/stores/chat";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const levelColors: Record<string, string> = {
    info: "text-accent",
    warn: "text-yellow-500",
    error: "text-error-fg",
    sent: "text-success",
    recv: "text-muted",
};

export function LogsPanel() {
    const [open, setOpen] = useState(false);
    const logs = useChatStore((s) => s.logs);
    const clearLogs = useChatStore((s) => s.clearLogs);
    const bodyRef = useRef<HTMLDivElement>(null);

    // Auto-scroll on new logs
    useEffect(() => {
        if (open && bodyRef.current) {
            bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
        }
    }, [logs.length, open]);

    return (
        <div className="border-t border-border">
            {/* Toggle bar */}
            <button
                className="w-full flex items-center justify-center gap-2 py-1.5 text-xs text-muted hover:bg-surface cursor-pointer bg-transparent border-none"
                onClick={() => setOpen((o) => !o)}
                aria-label={open ? "Collapse logs" : "Expand logs"}
            >
                <span className="flex items-center gap-1">{open ? <ChevronDown size={14} /> : <ChevronUp size={14} />} Logs</span>
                {logs.length > 0 && <Badge color="muted">{logs.length}</Badge>}
            </button>

            {/* Log entries */}
            {open && (
                <div className="border-t border-border">
                    <div className="flex items-center justify-between px-3 py-1.5 bg-surface">
                        <span className="text-xs text-muted font-medium">
                            Logs <Badge color="muted">{logs.length}</Badge>
                        </span>
                        <Button variant="ghost" onClick={clearLogs}>
                            Clear
                        </Button>
                    </div>
                    <div
                        ref={bodyRef}
                        className="max-h-40 overflow-y-auto px-3 py-1 text-xs font-mono"
                    >
                        {logs.map((log) => (
                            <div key={log.id} className="flex gap-2 py-0.5">
                                <span className="text-muted whitespace-nowrap">
                                    {new Date(log.timestamp).toLocaleTimeString()}
                                </span>
                                <span className={levelColors[log.level] || "text-text"}>
                                    {log.text}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
