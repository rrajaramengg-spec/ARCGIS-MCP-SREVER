import type { MessageRole } from "@/types/chat";

interface MessageBubbleProps {
    role: MessageRole;
    children: React.ReactNode;
}

const roleClasses: Record<MessageRole, string> = {
    user: "bg-accent text-white self-end rounded-2xl",
    assistant: "bg-surface text-text self-start rounded-xl shadow-sm border border-border",
    error: "bg-error-bg text-error-fg self-start rounded-xl border border-error-fg/30",
    system: "bg-muted/10 text-muted self-center rounded-xl text-center italic",
};

export function MessageBubble({ role, children }: MessageBubbleProps) {
    return (
        <div
            className={`px-3 py-2 max-w-[85%] text-sm break-words ${roleClasses[role]}`}
            data-role={role}
        >
            {children}
        </div>
    );
}
