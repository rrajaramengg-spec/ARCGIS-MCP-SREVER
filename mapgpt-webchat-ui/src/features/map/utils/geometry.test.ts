import { describe, expect, it } from "vitest";
import { mapGeometryType } from "./geometry";

describe("mapGeometryType", () => {
    it("maps point types", () => {
        expect(mapGeometryType("esriGeometryPoint")).toBe("point");
    });

    it("maps multipoint types", () => {
        expect(mapGeometryType("esriGeometryMultipoint")).toBe("multipoint");
    });

    it("maps polyline types", () => {
        expect(mapGeometryType("esriGeometryPolyline")).toBe("polyline");
    });

    it("maps polygon types", () => {
        expect(mapGeometryType("esriGeometryPolygon")).toBe("polygon");
    });

    it("defaults to point for null", () => {
        expect(mapGeometryType(null)).toBe("point");
    });

    it("defaults to point for unknown type", () => {
        expect(mapGeometryType("unknown")).toBe("point");
    });
});
