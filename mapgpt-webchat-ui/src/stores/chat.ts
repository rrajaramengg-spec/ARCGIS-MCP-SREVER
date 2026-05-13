/** Chat Zustand store — messages, logs, UI state */

import type { ExecuteResponse } from "@/types/api";
import type { ChatMessage, LogEntry } from "@/types/chat";
import { create } from "zustand";

interface ChatState {
    messages: ChatMessage[];
    logs: LogEntry[];
    isThinking: boolean;
    progressStep: string | null;
    inputText: string;
    isSendDisabled: boolean;

    addUserMessage: (text: string) => void;
    addAssistantMessage: (text: string, rawData: ExecuteResponse | null, queryId: string | null) => void;
    addErrorMessage: (text: string) => void;
    addSystemMessage: (text: string) => void;
    clearMessages: () => void;

    addLog: (level: LogEntry["level"], text: string) => void;
    clearLogs: () => void;

    setThinking: (thinking: boolean) => void;
    setProgressStep: (step: string | null) => void;
    setInputText: (text: string) => void;
    appendInputText: (text: string) => void;
    setSendDisabled: (disabled: boolean) => void;
}

let nextId = 0;
function genId(): string {
    return `msg-${++nextId}`;
}

function genLogId(): string {
    return `log-${++nextId}`;
}

export const useChatStore = create<ChatState>((set) => ({
    messages: [],
    logs: [],
    isThinking: false,
    progressStep: null,
    inputText: "",
    isSendDisabled: false,

    addUserMessage: (text: string) =>
        set((s) => ({
            messages: [
                ...s.messages,
                { id: genId(), role: "user", text, timestamp: Date.now() },
            ],
        })),

    addAssistantMessage: (text: string, rawData: ExecuteResponse | null, queryId: string | null) =>
        set((s) => ({
            messages: [
                ...s.messages,
                { id: genId(), role: "assistant", text, rawData, queryId, timestamp: Date.now() },
            ],
            isThinking: false,
            progressStep: null,
        })),

    addErrorMessage: (text: string) =>
        set((s) => ({
            messages: [
                ...s.messages,
                { id: genId(), role: "error", text, timestamp: Date.now() },
            ],
            isThinking: false,
            progressStep: null,
        })),

    addSystemMessage: (text: string) =>
        set((s) => ({
            messages: [
                ...s.messages,
                { id: genId(), role: "system", text, timestamp: Date.now() },
            ],
        })),

    clearMessages: () => set({ messages: [] }),

    addLog: (level: LogEntry["level"], text: string) =>
        set((s) => ({
            logs: [
                ...s.logs,
                { id: genLogId(), level, text, timestamp: Date.now() },
            ],
        })),

    clearLogs: () => set({ logs: [] }),

    setThinking: (thinking: boolean) => set({ isThinking: thinking }),
    setProgressStep: (step: string | null) => set({ progressStep: step }),
    setInputText: (text: string) => set({ inputText: text }),
    appendInputText: (text: string) =>
        set((s) => ({ inputText: s.inputText ? `${s.inputText} ${text}` : text })),
    setSendDisabled: (disabled: boolean) => set({ isSendDisabled: disabled }),
}));
