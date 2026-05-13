import { useChatStore } from "@/stores/chat";
import { useEffect, useRef, type ReactNode } from "react";

interface MessageListProps {
    children: ReactNode;
}

export function MessageList({ children }: MessageListProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const messageCount = useChatStore((s) => s.messages.length);
    const isThinking = useChatStore((s) => s.isThinking);

    // Auto-scroll on new messages or thinking state change
    useEffect(() => {
        const el = containerRef.current;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }, [messageCount, isThinking]);

    return (
        <div
            ref={containerRef}
            className="flex-1 overflow-y-auto p-4 flex flex-col gap-3"
        >
            {children}
        </div>
    );
}
