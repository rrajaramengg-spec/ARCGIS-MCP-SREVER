/**
 * Response normalization — port from static/js/normalize.js
 * Extracts renderable layer groups from backend response shapes.
 */

import type {
    ExecuteResponse,
    Feature,
    FeatureSetResult,
    GeocodeResult,
} from "@/types/api";
import type { LayerGroup, NormalizedResponse } from "@/types/map";

function inferGeometryType(features: Feature[]): string | null {
    if (!features || features.length === 0) return null;
    const geom = features[0]?.geometry;
    if (!geom) return null;
    if ("rings" in geom) return "esriGeometryPolygon";
    if ("paths" in geom) return "esriGeometryPolyline";
    if ("x" in geom && "y" in geom) return "esriGeometryPoint";
    return null;
}

/** Convert a feature_set result entry to a renderable layer group. */
export function featureSetToLayer(r: FeatureSetResult): LayerGroup {
    const features = Array.isArray(r.features) ? r.features : [];
    const role = r.role || "result";
    return {
        name: r.layer_name || r.layer || "Query",
        features,
        geometryType: r.geometryType || inferGeometryType(features),
        fields: r.fields || [],
        spatialReference: r.spatialReference || null,
        role: role === "buffer" || role === "source" ? "parent" : "child",
        count: r.count != null ? r.count : features.length,
        countOnly: features.length === 0 && (r.count ?? 0) > 0 && r.geometryType == null,
        bufferZone: role === "buffer",
        proximityLines: role === "distance_line",
        sourceLocation: role === "source",
    };
}

/** Convert a geocode result entry to a renderable point layer. */
export function geocodeToLayer(r: GeocodeResult): LayerGroup {
    const loc = r.location || { x: 0, y: 0 };
    return {
        name: r.address || "Location",
        features: [
            {
                geometry: { x: loc.x, y: loc.y, spatialReference: { wkid: 4326 } },
                attributes: { address: r.address || "", score: r.score || 0 },
            },
        ],
        geometryType: "esriGeometryPoint",
        fields: [],
        spatialReference: { wkid: 4326 },
        role: "parent",
        sourceLocation: true,
        count: 1,
    };
}

/** Normalize a single legacy result into an array of layer groups. */
function normalizeSingle(data: Record<string, unknown>): NormalizedResponse | null {
    if (!data || typeof data !== "object") return null;
    if (data.error) return null;

    // Count-only
    if (data.type === "count" && !Array.isArray(data.features)) {
        if (data.count != null) {
            return {
                layers: [
                    {
                        name: (data.layer as string) || "Query",
                        features: [],
                        geometryType: null,
                        fields: [],
                        spatialReference: null,
                        role: "primary",
                        count: data.count as number,
                        countOnly: true,
                    },
                ],
            };
        }
        return null;
    }

    // Spatial join
    if (data.type === "spatial_join" && data.parent) {
        const layers: LayerGroup[] = [];
        const parent = data.parent as Record<string, unknown>;
        const parentFeatures = Array.isArray(parent.features) ? (parent.features as Feature[]) : [];
        layers.push({
            name: (data.layer as string) || "Parent",
            features: parentFeatures,
            geometryType:
                (parent.geometryType as string) || inferGeometryType(parentFeatures),
            fields: (parent.fields as LayerGroup["fields"]) || [],
            spatialReference: (parent.spatialReference as LayerGroup["spatialReference"]) || null,
            role: "parent",
            count: parent.count != null ? (parent.count as number) : parentFeatures.length,
        });

        if (Array.isArray(data.children)) {
            for (const child of data.children as Record<string, unknown>[]) {
                const childFeatures = Array.isArray(child.features) ? (child.features as Feature[]) : [];
                layers.push({
                    name: (child.layer as string) || "Child",
                    features: childFeatures,
                    geometryType:
                        (child.geometryType as string) || inferGeometryType(childFeatures),
                    fields: (child.fields as LayerGroup["fields"]) || [],
                    spatialReference: (child.spatialReference as LayerGroup["spatialReference"]) || null,
                    role: "child",
                    count: child.count != null ? (child.count as number) : childFeatures.length,
                });
            }
        }
        return layers.length > 0 ? { layers } : null;
    }

    // Flat query with features
    if (Array.isArray(data.features)) {
        const features = data.features as Feature[];
        return {
            layers: [
                {
                    name: (data.layer as string) || "Query",
                    features,
                    geometryType:
                        (data.geometryType as string) || inferGeometryType(features),
                    fields: (data.fields as LayerGroup["fields"]) || [],
                    spatialReference: (data.spatialReference as LayerGroup["spatialReference"]) || null,
                    role: "primary",
                    count: data.count != null ? (data.count as number) : features.length,
                },
            ],
        };
    }

    return null;
}

/**
 * Normalize a query response into renderable layer groups.
 * Supports new typed results[] format and legacy shapes.
 */
export function normalizeQueryResponse(
    data: ExecuteResponse | Record<string, unknown> | null | undefined,
): NormalizedResponse | null {
    if (!data || typeof data !== "object") return null;
    if ("error" in data && data.error) return null;

    // New typed results[]
    const results = (data as ExecuteResponse).results;
    if (Array.isArray(results) && results.length > 0 && results[0]?.type) {
        const layers: LayerGroup[] = [];
        for (const r of results) {
            if (!r || typeof r !== "object") continue;
            if (r.type === "geocode") layers.push(geocodeToLayer(r));
            else if (r.type === "feature_set") layers.push(featureSetToLayer(r));
        }
        return layers.length > 0 ? { layers } : null;
    }

    // Legacy uniform { source, results[] }
    const rawData = data as Record<string, unknown>;
    if (rawData.source !== undefined && Array.isArray(rawData.results)) {
        const allLayers: LayerGroup[] = [];
        const source = rawData.source as Record<string, unknown> | null;

        if (source?.features && Array.isArray(source.features)) {
            const sf = source.features as Feature[];
            allLayers.push({
                name: (source.layer as string) || "Source",
                features: sf,
                geometryType: inferGeometryType(sf),
                fields: [],
                spatialReference: null,
                role: "parent",
                count: sf.length,
            });
        }

        if (
            source?.location &&
            (source.type === "geocode" ||
                source.type === "coordinates" ||
                source.type === "reverse_geocode") &&
            !(source.features && (source.features as Feature[]).length > 0)
        ) {
            const loc = source.location as { x: number; y: number };
            allLayers.push({
                name: (source.address as string) || "Location",
                features: [
                    {
                        geometry: { x: loc.x, y: loc.y, spatialReference: { wkid: 4326 } },
                        attributes: { address: (source.address as string) || "", score: (source.score as number) || 0 },
                    },
                ],
                geometryType: "esriGeometryPoint",
                fields: [],
                spatialReference: { wkid: 4326 },
                role: "parent",
                sourceLocation: true,
                count: 1,
            });
        }

        for (const result of rawData.results as Record<string, unknown>[]) {
            if (!result || typeof result !== "object") continue;
            const features = Array.isArray(result.features) ? (result.features as Feature[]) : [];
            const isBufferZone =
                result.type === "buffer_zone" || result.layer === "_buffer_zone";
            const isProximityLines =
                result.type === "proximity_lines" || result.layer === "_proximity_lines";
            allLayers.push({
                name: (result.layer as string) || "Result",
                features,
                geometryType:
                    (result.geometryType as string) || inferGeometryType(features),
                fields: (result.fields as LayerGroup["fields"]) || [],
                spatialReference: (result.spatialReference as LayerGroup["spatialReference"]) || null,
                role: isBufferZone ? "parent" : "child",
                count: result.count != null ? (result.count as number) : features.length,
                countOnly: result.type === "count",
                joinType: (result.join_type as string) || null,
                totalInRadius: (result.total_in_radius as number) || null,
                searchRadius: (result.search_radius as number) || null,
                searchUnit: (result.search_unit as string) || null,
                bufferZone: isBufferZone,
                proximityLines: isProximityLines,
            });
        }

        return allLayers.length > 0
            ? { layers: allLayers, source: source as Record<string, unknown> | undefined }
            : null;
    }

    // Multi-result wrapper (legacy)
    if (Array.isArray(rawData.results)) {
        const allLayers: LayerGroup[] = [];
        for (const result of rawData.results as Record<string, unknown>[]) {
            const normalized = normalizeSingle(result);
            if (normalized) allLayers.push(...normalized.layers);
        }
        return allLayers.length > 0 ? { layers: allLayers } : null;
    }

    // Single result (legacy)
    return normalizeSingle(rawData);
}

/** Extract graph execution metadata from a response. */
export function extractExecutionGraph(
    response: ExecuteResponse | null | undefined,
): ExecuteResponse["execution_graph"] | null {
    if (!response || typeof response !== "object") return null;
    return response.execution_graph || null;
}
