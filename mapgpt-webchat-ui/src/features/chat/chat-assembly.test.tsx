import { useChatStore } from "@/stores/chat";
import type { WsMessage } from "@/types/api";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";
import { createMessageHandler } from "./handleResponse";

// Mock react-markdown and rehype-highlight
vi.mock("react-markdown", () => ({
    default: ({ children }: { children: string }) => <p>{children}</p>,
}));
vi.mock("rehype-highlight", () => ({ default: () => { } }));

beforeEach(() => {
    useChatStore.setState({
        messages: [],
        logs: [],
        isThinking: false,
        progressStep: null,
        inputText: "",
        isSendDisabled: false,
    });
});

describe("ChatPanel", () => {
    it("renders welcome message", () => {
        render(<ChatPanel />);
        expect(
            screen.getByText(
                "Welcome to MapGPT Chat! Type a question about your spatial data.",
            ),
        ).toBeDefined();
    });

    it("renders user messages from store", () => {
        useChatStore.getState().addUserMessage("test query");
        render(<ChatPanel />);
        expect(screen.getByText("test query")).toBeDefined();
    });

    it("renders thinking indicator when isThinking", () => {
        useChatStore.setState({ isThinking: true });
        render(<ChatPanel />);
        expect(screen.getByLabelText("Thinking")).toBeDefined();
    });

    it("renders progress step", () => {
        useChatStore.setState({ isThinking: true, progressStep: "Querying..." });
        render(<ChatPanel />);
        expect(screen.getByText("Querying...")).toBeDefined();
    });
});

describe("createMessageHandler", () => {
    it("handles response messages", () => {
        const handler = createMessageHandler();
        const msg: WsMessage = {
            type: "response",
            data: {
                action: "query",
                message: "Found 5 features",
                data: null,
                results: [],
                execution_time_ms: 100,
                timing: { total_ms: 100 },
                query_id: "q1",
                tool_name: null,
                tool_args: null,
            },
        };
        useChatStore.setState({ isThinking: true, isSendDisabled: true });
        handler(msg);
        const state = useChatStore.getState();
        expect(state.messages).toHaveLength(1);
        expect(state.messages[0].text).toBe("Found 5 features");
        expect(state.isThinking).toBe(false);
        expect(state.isSendDisabled).toBe(false);
    });

    it("handles progress messages", () => {
        const handler = createMessageHandler();
        const msg: WsMessage = {
            type: "progress",
            data: { step: "Building query plan..." },
        };
        handler(msg);
        expect(useChatStore.getState().progressStep).toBe(
            "Building query plan...",
        );
    });

    it("handles error messages", () => {
        const handler = createMessageHandler();
        const msg: WsMessage = {
            type: "error",
            data: { error: "Connection failed" },
        };
        handler(msg);
        const state = useChatStore.getState();
        expect(state.messages).toHaveLength(1);
        expect(state.messages[0].role).toBe("error");
        expect(state.isSendDisabled).toBe(false);
    });

    it("calls onShowOnMap for query actions with results", () => {
        const onShowOnMap = vi.fn();
        const handler = createMessageHandler({ onShowOnMap });
        const data = {
            action: "query" as const,
            message: "Found",
            data: null,
            results: [
                {
                    type: "feature_set" as const,
                    layer: "test",
                    features: [{ attributes: { a: 1 } }],
                    count: 1,
                    role: "result",
                    geometryType: "esriGeometryPoint",
                    fields: [],
                    spatialReference: { wkid: 4326 },
                },
            ],
            execution_time_ms: 100,
            timing: { total_ms: 100 },
            query_id: "q1",
            tool_name: null,
            tool_args: null,
        };
        handler({ type: "response", data });
        expect(onShowOnMap).toHaveBeenCalledWith(data);
    });
});
