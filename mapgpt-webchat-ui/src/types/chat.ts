import type { ExecuteResponse } from "./api";

/** Roles for chat message bubbles */
export type MessageRole = "user" | "assistant" | "error" | "system";

/** A single chat message displayed in the message list */
export interface ChatMessage {
    id: string;
    role: MessageRole;
    text: string;
    rawData?: ExecuteResponse | null;
    queryId?: string | null;
    timestamp: number;
}

/** A slash command fetched from /api/commands */
export interface Command {
    name: string;
    description?: string;
}

/** A resource fetched from /api/resources */
export interface Resource {
    name: string;
    description?: string;
    uri?: string;
}

/** A log entry displayed in the logs panel */
export interface LogEntry {
    id: string;
    level: "info" | "warn" | "error" | "sent" | "recv";
    text: string;
    timestamp: number;
}
