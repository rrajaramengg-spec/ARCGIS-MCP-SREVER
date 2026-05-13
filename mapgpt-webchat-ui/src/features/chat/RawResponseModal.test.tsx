import type { ExecuteResponse } from "@/types/api";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RawResponseModal } from "./RawResponseModal";

describe("RawResponseModal", () => {
    it("displays double quotes as literal \" not &quot;", () => {
        const data: ExecuteResponse = {
            action: "query",
            message: "Found features",
            data: { key: "value" },
        } as ExecuteResponse;

        render(
            <RawResponseModal open={true} onClose={vi.fn()} data={data} />,
        );

        const code = document.querySelector("code.hljs");
        expect(code).not.toBeNull();
        expect(code!.textContent).toContain('"');
        expect(code!.textContent).not.toContain("&quot;");
    });

    it("renders syntax-highlighted JSON with hljs classes", () => {
        const data: ExecuteResponse = {
            action: "query",
            message: "test",
        } as ExecuteResponse;

        render(
            <RawResponseModal open={true} onClose={vi.fn()} data={data} />,
        );

        const code = document.querySelector("code.hljs.language-json");
        expect(code).not.toBeNull();
        expect(code!.innerHTML).toContain("hljs-");
    });
});
