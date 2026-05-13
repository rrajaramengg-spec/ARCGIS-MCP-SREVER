import type { LayerGroup } from "@/types/map";
import { describe, expect, it } from "vitest";
import { buildPopupTemplate, findTitleField } from "./popup";

function makeLayer(overrides: Partial<LayerGroup> = {}): LayerGroup {
    return {
        name: "Test",
        features: [],
        geometryType: "esriGeometryPoint",
        fields: [],
        spatialReference: null,
        role: "child",
        count: 0,
        ...overrides,
    };
}

describe("findTitleField", () => {
    it("returns NAME field when present", () => {
        const layer = makeLayer({
            fields: [
                { name: "OBJECTID", type: "esriFieldTypeOID" },
                { name: "NAME", type: "esriFieldTypeString" },
            ],
        });
        expect(findTitleField(layer)).toBe("NAME");
    });

    it("returns first string field when no NAME", () => {
        const layer = makeLayer({
            fields: [
                { name: "OBJECTID", type: "esriFieldTypeOID" },
                { name: "Label", type: "esriFieldTypeString" },
            ],
        });
        expect(findTitleField(layer)).toBe("Label");
    });

    it("returns null when no fields", () => {
        expect(findTitleField(makeLayer())).toBeNull();
    });
});

describe("buildPopupTemplate", () => {
    it("returns null for buffer zones", () => {
        const layer = makeLayer({ bufferZone: true });
        expect(buildPopupTemplate(layer)).toBeNull();
    });

    it("returns distance popup for proximity lines", () => {
        const layer = makeLayer({ proximityLines: true });
        const template = buildPopupTemplate(layer);
        expect(template?.title).toBe("Proximity Line");
        expect(template?.content).toContain("{distance}");
    });

    it("uses field metadata when available", () => {
        const layer = makeLayer({
            fields: [
                { name: "NAME", alias: "Name", type: "esriFieldTypeString" },
                { name: "POP", alias: "Population", type: "esriFieldTypeInteger" },
            ],
        });
        const template = buildPopupTemplate(layer);
        expect(template?.title).toBe("{NAME}");
        expect(Array.isArray(template?.content)).toBe(true);
    });

    it("derives from first feature attributes when no fields", () => {
        const layer = makeLayer({
            features: [{ attributes: { city: "Test", state: "NY" } }],
        });
        const template = buildPopupTemplate(layer);
        expect(template?.content).toContain("{city}");
    });

    it("returns wildcard for empty layers", () => {
        const layer = makeLayer();
        const template = buildPopupTemplate(layer);
        expect(template?.content).toBe("{*}");
    });
});
