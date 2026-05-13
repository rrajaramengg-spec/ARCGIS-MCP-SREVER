import { beforeEach, describe, expect, it } from "vitest";
import { useChatStore } from "./chat";

beforeEach(() => {
    // Reset store to initial state between tests
    useChatStore.setState({
        messages: [],
        logs: [],
        isThinking: false,
        progressStep: null,
        inputText: "",
        isSendDisabled: false,
    });
});

describe("useChatStore", () => {
    it("adds a user message", () => {
        useChatStore.getState().addUserMessage("hello");
        const messages = useChatStore.getState().messages;
        expect(messages).toHaveLength(1);
        expect(messages[0].role).toBe("user");
        expect(messages[0].text).toBe("hello");
    });

    it("adds an assistant message and clears thinking", () => {
        useChatStore.setState({ isThinking: true, progressStep: "Processing..." });
        useChatStore.getState().addAssistantMessage("Found 5 features", null, "q1");
        const state = useChatStore.getState();
        expect(state.messages).toHaveLength(1);
        expect(state.messages[0].role).toBe("assistant");
        expect(state.messages[0].queryId).toBe("q1");
        expect(state.isThinking).toBe(false);
        expect(state.progressStep).toBeNull();
    });

    it("adds an error message and clears thinking", () => {
        useChatStore.setState({ isThinking: true });
        useChatStore.getState().addErrorMessage("Something failed");
        const state = useChatStore.getState();
        expect(state.messages[0].role).toBe("error");
        expect(state.isThinking).toBe(false);
    });

    it("clears all messages", () => {
        useChatStore.getState().addUserMessage("a");
        useChatStore.getState().addUserMessage("b");
        useChatStore.getState().clearMessages();
        expect(useChatStore.getState().messages).toHaveLength(0);
    });

    it("adds and clears logs", () => {
        useChatStore.getState().addLog("info", "Connected");
        useChatStore.getState().addLog("error", "Failed");
        expect(useChatStore.getState().logs).toHaveLength(2);
        useChatStore.getState().clearLogs();
        expect(useChatStore.getState().logs).toHaveLength(0);
    });

    it("manages thinking state", () => {
        useChatStore.getState().setThinking(true);
        expect(useChatStore.getState().isThinking).toBe(true);
        useChatStore.getState().setProgressStep("Querying...");
        expect(useChatStore.getState().progressStep).toBe("Querying...");
    });

    it("manages input text", () => {
        useChatStore.getState().setInputText("test query");
        expect(useChatStore.getState().inputText).toBe("test query");
    });

    it("appends to input text", () => {
        useChatStore.getState().setInputText("find");
        useChatStore.getState().appendInputText("-75.1, 40.0");
        expect(useChatStore.getState().inputText).toBe("find -75.1, 40.0");
    });

    it("appends to empty input text without leading space", () => {
        useChatStore.getState().appendInputText("-75.1, 40.0");
        expect(useChatStore.getState().inputText).toBe("-75.1, 40.0");
    });

    it("manages send disabled state", () => {
        useChatStore.getState().setSendDisabled(true);
        expect(useChatStore.getState().isSendDisabled).toBe(true);
    });
});
