import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "./Badge";

describe("Badge", () => {
    it("renders children text", () => {
        render(<Badge>42</Badge>);
        expect(screen.getByText("42")).toBeDefined();
    });

    it("applies primary color by default", () => {
        render(<Badge>Count</Badge>);
        expect(screen.getByText("Count").className).toContain("text-accent");
    });

    it("applies parent color", () => {
        render(<Badge color="parent">Parent</Badge>);
        expect(screen.getByText("Parent").className).toContain("text-accent-hi");
    });

    it("applies buffer color", () => {
        render(<Badge color="buffer">Buffer</Badge>);
        expect(screen.getByText("Buffer").className).toContain("text-muted");
    });

    it("merges custom className", () => {
        render(<Badge className="extra">Tag</Badge>);
        expect(screen.getByText("Tag").className).toContain("extra");
    });
});
