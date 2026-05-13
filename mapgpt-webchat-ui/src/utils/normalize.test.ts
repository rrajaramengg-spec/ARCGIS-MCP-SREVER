import type { ExecuteResponse, FeatureSetResult, GeocodeResult } from "@/types/api";
import { describe, expect, it } from "vitest";
import {
    extractExecutionGraph,
    featureSetToLayer,
    geocodeToLayer,
    normalizeQueryResponse,
} from "./normalize";

describe("featureSetToLayer", () => {
    it("converts a feature_set result to a layer group", () => {
        const input: FeatureSetResult = {
            type: "feature_set",
            layer: "Fire Stations",
            features: [{ geometry: { x: -75, y: 40 }, attributes: { name: "Station 1" } }],
            geometryType: "esriGeometryPoint",
            fields: [{ name: "name", alias: "Name" }],
            spatialReference: { wkid: 4326 },
            role: "result",
            count: 1,
        };
        const layer = featureSetToLayer(input);
        expect(layer.name).toBe("Fire Stations");
        expect(layer.role).toBe("child");
        expect(layer.count).toBe(1);
        expect(layer.features).toHaveLength(1);
    });

    it("maps buffer role to parent", () => {
        const input: FeatureSetResult = {
            type: "feature_set",
            features: [],
            role: "buffer",
        };
        const layer = featureSetToLayer(input);
        expect(layer.role).toBe("parent");
        expect(layer.bufferZone).toBe(true);
    });

    it("detects count-only layers", () => {
        const input: FeatureSetResult = {
            type: "feature_set",
            features: [],
            count: 42,
        };
        const layer = featureSetToLayer(input);
        expect(layer.countOnly).toBe(true);
        expect(layer.count).toBe(42);
    });

    it("uses layer_name when present", () => {
        const input: FeatureSetResult = {
            type: "feature_set",
            layer_name: "PSAP",
            layer: "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0",
            features: [],
        };
        const layer = featureSetToLayer(input);
        expect(layer.name).toBe("PSAP");
    });

    it("falls back to layer when layer_name absent", () => {
        const input: FeatureSetResult = {
            type: "feature_set",
            layer: "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0",
            features: [],
        };
        const layer = featureSetToLayer(input);
        expect(layer.name).toBe("https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0");
    });

    it("falls back to 'Query' when both layer_name and layer absent", () => {
        const input: FeatureSetResult = {
            type: "feature_set",
            features: [],
        };
        const layer = featureSetToLayer(input);
        expect(layer.name).toBe("Query");
    });
});

describe("geocodeToLayer", () => {
    it("converts a geocode result to a point layer", () => {
        const input: GeocodeResult = {
            type: "geocode",
            location: { x: -75.1, y: 40.0 },
            address: "123 Main St",
            score: 95,
        };
        const layer = geocodeToLayer(input);
        expect(layer.name).toBe("123 Main St");
        expect(layer.role).toBe("parent");
        expect(layer.sourceLocation).toBe(true);
        expect(layer.features[0].geometry).toEqual({
            x: -75.1,
            y: 40.0,
            spatialReference: { wkid: 4326 },
        });
    });
});

describe("normalizeQueryResponse", () => {
    it("returns null for null/undefined input", () => {
        expect(normalizeQueryResponse(null)).toBeNull();
        expect(normalizeQueryResponse(undefined)).toBeNull();
    });

    it("returns null for error responses", () => {
        expect(
            normalizeQueryResponse({ error: "Something failed" } as unknown as ExecuteResponse),
        ).toBeNull();
    });

    it("normalizes new typed results[] format", () => {
        const response: ExecuteResponse = {
            action: "query",
            message: "Found 2 features",
            results: [
                {
                    type: "feature_set",
                    layer: "Schools",
                    features: [{ attributes: { name: "A" } }],
                    count: 1,
                },
                {
                    type: "geocode",
                    location: { x: -75, y: 40 },
                    address: "Test",
                    score: 100,
                },
            ],
        };
        const result = normalizeQueryResponse(response);
        expect(result).not.toBeNull();
        expect(result!.layers).toHaveLength(2);
        expect(result!.layers[0].name).toBe("Schools");
        expect(result!.layers[1].name).toBe("Test");
    });

    it("normalizes flat query with features (legacy)", () => {
        const data = {
            features: [{ geometry: { x: 1, y: 2 }, attributes: { id: 1 } }],
            geometryType: "esriGeometryPoint",
            layer: "Test Layer",
        };
        const result = normalizeQueryResponse(data as unknown as ExecuteResponse);
        expect(result).not.toBeNull();
        expect(result!.layers).toHaveLength(1);
        expect(result!.layers[0].name).toBe("Test Layer");
    });

    it("normalizes legacy source + results format", () => {
        const data = {
            source: {
                type: "geocode",
                location: { x: -75, y: 40 },
                address: "Main St",
            },
            results: [
                {
                    layer: "Nearby",
                    features: [{ attributes: { name: "A" } }],
                },
            ],
        };
        const result = normalizeQueryResponse(data as unknown as ExecuteResponse);
        expect(result).not.toBeNull();
        expect(result!.layers).toHaveLength(2);
        expect(result!.layers[0].sourceLocation).toBe(true);
        expect(result!.layers[1].name).toBe("Nearby");
    });

    it("normalizes count-only response (legacy)", () => {
        const data = { type: "count", count: 50, layer: "Parcels" };
        const result = normalizeQueryResponse(data as unknown as ExecuteResponse);
        expect(result).not.toBeNull();
        expect(result!.layers[0].countOnly).toBe(true);
        expect(result!.layers[0].count).toBe(50);
    });
});

describe("extractExecutionGraph", () => {
    it("returns null for null input", () => {
        expect(extractExecutionGraph(null)).toBeNull();
    });

    it("extracts execution_graph when present", () => {
        const response: ExecuteResponse = {
            action: "query",
            message: "test",
            execution_graph: { nodes_executed: 3, parallel_groups: 1 },
        };
        const graph = extractExecutionGraph(response);
        expect(graph).toEqual({ nodes_executed: 3, parallel_groups: 1 });
    });
});
