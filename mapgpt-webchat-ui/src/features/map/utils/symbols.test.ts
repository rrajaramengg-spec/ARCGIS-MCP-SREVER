import { describe, expect, it } from "vitest";
import {
    BUFFER_SYMBOL,
    buildDistanceLabelSymbol,
    buildParentSymbol,
    buildSymbol,
    hexToRgba,
    LAYER_COLORS,
    LOCATE_SYMBOL,
    PROXIMITY_HIGHLIGHT_SYMBOL,
    PROXIMITY_LINE_SYMBOL
} from "./symbols";

describe("hexToRgba", () => {
    it("converts hex to RGBA array", () => {
        expect(hexToRgba("#00897B", 0.8)).toEqual([0, 137, 123, 0.8]);
        expect(hexToRgba("#FFFFFF", 1.0)).toEqual([255, 255, 255, 1.0]);
        expect(hexToRgba("#000000", 0)).toEqual([0, 0, 0, 0]);
    });
});

describe("buildSymbol", () => {
    it("returns simple-marker for point geometry", () => {
        const sym = buildSymbol("esriGeometryPoint", "#00897B");
        expect(sym.type).toBe("simple-marker");
    });

    it("returns simple-line for polyline geometry", () => {
        const sym = buildSymbol("esriGeometryPolyline", "#E64A19");
        expect(sym.type).toBe("simple-line");
    });

    it("returns simple-fill for polygon geometry", () => {
        const sym = buildSymbol("esriGeometryPolygon", "#3949AB");
        expect(sym.type).toBe("simple-fill");
    });

    it("defaults to simple-marker for null", () => {
        const sym = buildSymbol(null, "#F9A825");
        expect(sym.type).toBe("simple-marker");
    });
});

describe("buildParentSymbol", () => {
    it("returns dashed fill for polygon parent", () => {
        const sym = buildParentSymbol("esriGeometryPolygon");
        expect(sym.type).toBe("simple-fill");
    });

    it("returns marker for point parent", () => {
        const sym = buildParentSymbol("esriGeometryPoint");
        expect(sym.type).toBe("simple-marker");
    });

    it("returns dashed line for polyline parent", () => {
        const sym = buildParentSymbol("esriGeometryPolyline");
        expect(sym.type).toBe("simple-line");
    });
});

describe("symbol constants", () => {
    it("has 6 layer colors", () => {
        expect(LAYER_COLORS).toHaveLength(6);
    });

    it("LOCATE_SYMBOL is a red marker", () => {
        expect(LOCATE_SYMBOL.type).toBe("simple-marker");
        expect(LOCATE_SYMBOL.color).toEqual([211, 47, 47]);
    });

    it("BUFFER_SYMBOL is a semi-transparent fill", () => {
        expect(BUFFER_SYMBOL.type).toBe("simple-fill");
        expect(BUFFER_SYMBOL.color[3]).toBeLessThan(0.5);
    });

    it("PROXIMITY_LINE_SYMBOL is a dashed line", () => {
        expect(PROXIMITY_LINE_SYMBOL.type).toBe("simple-line");
        expect(PROXIMITY_LINE_SYMBOL.style).toBe("dash");
    });

    it("PROXIMITY_HIGHLIGHT_SYMBOL is a solid orange line", () => {
        expect(PROXIMITY_HIGHLIGHT_SYMBOL.type).toBe("simple-line");
        expect(PROXIMITY_HIGHLIGHT_SYMBOL.style).toBe("solid");
        expect(PROXIMITY_HIGHLIGHT_SYMBOL.width).toBe(3);
    });
});

describe("buildDistanceLabelSymbol", () => {
    it("returns text symbol with correct text", () => {
        const sym = buildDistanceLabelSymbol("2.5 mi");
        expect(sym.type).toBe("text");
        expect(sym.text).toBe("2.5 mi");
    });

    it("includes halo for readability", () => {
        const sym = buildDistanceLabelSymbol("1.0 mi");
        expect(sym.haloColor).toBeDefined();
        expect(sym.haloSize).toBeGreaterThan(0);
    });
});
