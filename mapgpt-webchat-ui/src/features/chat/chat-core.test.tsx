import { useChatStore } from "@/stores/chat";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatInput } from "./ChatInput";
import { MessageBubble } from "./MessageBubble";
import { ProgressStep } from "./ProgressStep";
import { ThinkingIndicator } from "./ThinkingIndicator";

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

describe("MessageBubble", () => {
    it("renders user message with correct styling", () => {
        render(<MessageBubble role="user">Hello</MessageBubble>);
        const el = screen.getByText("Hello");
        expect(el.className).toContain("bg-accent");
        expect(el.dataset.role).toBe("user");
    });

    it("renders assistant message", () => {
        render(<MessageBubble role="assistant">Found 5 features</MessageBubble>);
        const el = screen.getByText("Found 5 features");
        expect(el.className).toContain("bg-surface");
        expect(el.dataset.role).toBe("assistant");
    });

    it("renders error message", () => {
        render(<MessageBubble role="error">Something failed</MessageBubble>);
        const el = screen.getByText("Something failed");
        expect(el.className).toContain("bg-error-bg");
    });

    it("renders system message centered", () => {
        render(<MessageBubble role="system">Welcome</MessageBubble>);
        const el = screen.getByText("Welcome");
        expect(el.className).toContain("text-center");
    });
});

describe("ThinkingIndicator", () => {
    it("renders three dots", () => {
        render(<ThinkingIndicator />);
        const el = screen.getByLabelText("Thinking");
        expect(el.children).toHaveLength(3);
    });
});

describe("ProgressStep", () => {
    it("renders step text", () => {
        render(<ProgressStep step="Querying features..." />);
        expect(screen.getByText("Querying features...")).toBeDefined();
    });
});

describe("ChatInput", () => {
    it("renders input and send button", () => {
        render(<ChatInput onSend={() => { }} />);
        expect(screen.getByLabelText("Chat input")).toBeDefined();
        expect(screen.getByRole("button", { name: "Send" })).toBeDefined();
    });

    it("calls onSend with text and clears input", async () => {
        const user = userEvent.setup();
        const onSend = vi.fn();
        render(<ChatInput onSend={onSend} />);
        const input = screen.getByLabelText("Chat input");
        await user.type(input, "test query");
        await user.click(screen.getByRole("button", { name: "Send" }));
        expect(onSend).toHaveBeenCalledWith("test query");
    });

    it("calls onSend on Enter key", async () => {
        const user = userEvent.setup();
        const onSend = vi.fn();
        render(<ChatInput onSend={onSend} />);
        const input = screen.getByLabelText("Chat input");
        await user.type(input, "test{Enter}");
        expect(onSend).toHaveBeenCalledWith("test");
    });

    it("does not send empty text", async () => {
        const user = userEvent.setup();
        const onSend = vi.fn();
        render(<ChatInput onSend={onSend} />);
        await user.click(screen.getByRole("button", { name: "Send" }));
        expect(onSend).not.toHaveBeenCalled();
    });

    it("disables send button when isSendDisabled", () => {
        useChatStore.setState({ isSendDisabled: true });
        render(<ChatInput onSend={() => { }} />);
        expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    });

    it("calls onInputChange on input change", async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<ChatInput onSend={() => { }} onInputChange={onChange} />);
        await user.type(screen.getByLabelText("Chat input"), "a");
        expect(onChange).toHaveBeenCalledWith("a");
    });
});
