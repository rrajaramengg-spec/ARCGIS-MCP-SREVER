import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
    it("renders children text", () => {
        render(<Button>Click me</Button>);
        expect(screen.getByRole("button", { name: "Click me" })).toBeDefined();
    });

    it("applies primary variant by default", () => {
        render(<Button>Go</Button>);
        const btn = screen.getByRole("button");
        expect(btn.className).toContain("bg-accent");
    });

    it("applies ghost variant", () => {
        render(<Button variant="ghost">Ghost</Button>);
        const btn = screen.getByRole("button");
        expect(btn.className).toContain("bg-transparent");
        expect(btn.className).toContain("text-accent");
    });

    it("applies icon variant", () => {
        render(<Button variant="icon">X</Button>);
        const btn = screen.getByRole("button");
        expect(btn.className).toContain("text-muted");
    });

    it("passes disabled prop through", () => {
        render(<Button disabled>Nope</Button>);
        expect(screen.getByRole("button")).toBeDisabled();
    });

    it("calls onClick handler", async () => {
        const user = userEvent.setup();
        let clicked = false;
        render(<Button onClick={() => { clicked = true; }}>Go</Button>);
        await user.click(screen.getByRole("button"));
        expect(clicked).toBe(true);
    });

    it("merges custom className", () => {
        render(<Button className="my-class">Go</Button>);
        expect(screen.getByRole("button").className).toContain("my-class");
    });
});
