import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

describe("Modal", () => {
    it("renders nothing when closed", () => {
        const { container } = render(
            <Modal open={false} onClose={() => { }} title="Test">
                <p>Content</p>
            </Modal>,
        );
        expect(container.innerHTML).toBe("");
    });

    it("renders title and content when open", () => {
        render(
            <Modal open={true} onClose={() => { }} title="My Modal">
                <p>Hello</p>
            </Modal>,
        );
        expect(screen.getByText("My Modal")).toBeDefined();
        expect(screen.getByText("Hello")).toBeDefined();
    });

    it("calls onClose when close button is clicked", async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        render(
            <Modal open={true} onClose={onClose} title="Test">
                <p>Content</p>
            </Modal>,
        );
        await user.click(screen.getByLabelText("Close"));
        expect(onClose).toHaveBeenCalledOnce();
    });

    it("calls onClose on Escape key", async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        render(
            <Modal open={true} onClose={onClose} title="Test">
                <p>Content</p>
            </Modal>,
        );
        await user.keyboard("{Escape}");
        expect(onClose).toHaveBeenCalledOnce();
    });

    it("calls onClose when backdrop is clicked", async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        render(
            <Modal open={true} onClose={onClose} title="Test">
                <p>Content</p>
            </Modal>,
        );
        // Click the backdrop (the outermost div with role="dialog")
        const dialog = screen.getByRole("dialog");
        await user.click(dialog);
        expect(onClose).toHaveBeenCalledOnce();
    });

    it("renders action buttons", () => {
        render(
            <Modal
                open={true}
                onClose={() => { }}
                title="Test"
                actions={<button>Copy</button>}
            >
                <p>Content</p>
            </Modal>,
        );
        expect(screen.getByText("Copy")).toBeDefined();
    });

    it("uses fullscreen classes when fullScreen is true", () => {
        render(
            <Modal open={true} onClose={() => { }} title="FS" fullScreen>
                <p>Full</p>
            </Modal>,
        );
        const dialog = screen.getByRole("dialog");
        const panel = dialog.querySelector("[class*='96vw']");
        expect(panel).toBeTruthy();
        // Content area should have overflow-hidden, not overflow-auto
        const content = dialog.querySelector("[class*='overflow-hidden']");
        expect(content).toBeTruthy();
    });
});
