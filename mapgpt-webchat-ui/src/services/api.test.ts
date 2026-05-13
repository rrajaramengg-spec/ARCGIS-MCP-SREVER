import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearCommandCache, fetchCommands, fetchResources } from "./api";

beforeEach(() => {
    clearCommandCache();
    vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("fetchCommands", () => {
    it("fetches commands from /api/commands", async () => {
        const mockCommands = [{ name: "/query", description: "Run a query" }];
        (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            json: () => Promise.resolve(mockCommands),
        });
        const cmds = await fetchCommands();
        expect(cmds).toEqual(mockCommands);
        expect(fetch).toHaveBeenCalledWith("/api/commands");
    });

    it("caches after first fetch", async () => {
        const mockCommands = [{ name: "/help" }];
        (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            json: () => Promise.resolve(mockCommands),
        });
        await fetchCommands();
        await fetchCommands();
        expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("returns empty array on error", async () => {
        (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("Network error"));
        const cmds = await fetchCommands();
        expect(cmds).toEqual([]);
    });
});

describe("fetchResources", () => {
    it("fetches resources from /api/resources", async () => {
        const mockResources = [{ name: "layers", uri: "/api/resources/layers" }];
        (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            json: () => Promise.resolve(mockResources),
        });
        const res = await fetchResources();
        expect(res).toEqual(mockResources);
    });

    it("returns empty array on error", async () => {
        (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("fail"));
        const res = await fetchResources();
        expect(res).toEqual([]);
    });
});
