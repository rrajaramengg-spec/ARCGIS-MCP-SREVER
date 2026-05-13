import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { Header } from "./Header";
import { PanelLayout } from "./PanelLayout";

// Mock the websocket store
vi.mock("@/stores/websocket", () => ({
    useWebSocketStore: (selector: (s: Record<string, unknown>) => unknown) =>
        selector({
            isConnected: true,
            sessionId: "abc12345-6789",
            send: vi.fn(),
            connect: vi.fn(),
            disconnect: vi.fn(),
            setMessageHandler: vi.fn(),
            messageHandler: null,
        }),
}));

describe("Header", () => {
    it("shows connected status", () => {
        render(<Header />);
        expect(screen.getByText("Connected")).toBeDefined();
        expect(screen.getByText("MapGPT Chat")).toBeDefined();
        expect(screen.getByText("DEMO")).toBeDefined();
    });

    it("shows truncated session ID", () => {
        render(<Header />);
        expect(screen.getByText("abc12345")).toBeDefined();
    });
});

describe("PanelLayout", () => {
    it("renders both panels in default mode", () => {
        render(
            <PanelLayout
                mode="default"
                onToggleChat={() => { }}
                onToggleMap={() => { }}
                chatPanel={<div>Chat</div>}
                mapPanel={<div>Map</div>}
            />,
        );
        expect(screen.getByText("Chat")).toBeDefined();
        expect(screen.getByText("Map")).toBeDefined();
    });

    it("hides map panel in chat-max mode", () => {
        render(
            <PanelLayout
                mode="chat-max"
                onToggleChat={() => { }}
                onToggleMap={() => { }}
                chatPanel={<div>Chat</div>}
                mapPanel={<div>Map</div>}
            />,
        );
        // Chat panel should be full width
        const chatContainer = screen.getByText("Chat").closest("div[class*='w-']");
        expect(chatContainer?.className).toContain("w-full");
    });

    it("calls onToggleChat when chat toggle is clicked", async () => {
        const user = userEvent.setup();
        const onToggle = vi.fn();
        render(
            <PanelLayout
                mode="default"
                onToggleChat={onToggle}
                onToggleMap={() => { }}
                chatPanel={<div>Chat</div>}
                mapPanel={<div>Map</div>}
            />,
        );
        await user.click(screen.getByLabelText("Maximize chat"));
        expect(onToggle).toHaveBeenCalledOnce();
    });
});

describe("AppShell", () => {
    it("renders header, chat, and map panels", () => {
        render(
            <AppShell
                chatPanel={<div>Chat Content</div>}
                mapPanel={<div>Map Content</div>}
            />,
        );
        expect(screen.getByText("MapGPT Chat")).toBeDefined();
        expect(screen.getByText("Chat Content")).toBeDefined();
        expect(screen.getByText("Map Content")).toBeDefined();
    });

    it("toggles layout mode on chat maximize click", async () => {
        const user = userEvent.setup();
        render(
            <AppShell
                chatPanel={<div>Chat Content</div>}
                mapPanel={<div>Map Content</div>}
            />,
        );
        // Click maximize chat
        await user.click(screen.getByLabelText("Maximize chat"));
        // Now should show "Restore panels" for chat
        expect(screen.getByLabelText("Restore panels")).toBeDefined();
    });
});
