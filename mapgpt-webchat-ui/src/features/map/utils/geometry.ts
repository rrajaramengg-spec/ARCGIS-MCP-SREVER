/** Geometry construction helpers — ported from static/js/map.js */

import type { Geometry } from "@/types/api";

/**
 * Map ArcGIS REST geometry type string to SDK geometry type.
 */
export function mapGeometryType(geomType: string | null): string {
    if (!geomType) return "point";
    const lower = geomType.toLowerCase();
    if (lower.includes("point") && lower.includes("multi")) return "multipoint";
    if (lower.includes("point")) return "point";
    if (lower.includes("polyline") || lower.includes("line")) return "polyline";
    if (lower.includes("polygon")) return "polygon";
    return "point";
}

/**
 * Construct an ArcGIS SDK geometry instance from REST JSON.
 * Returns the constructed geometry or the raw JSON for SDK autocasting.
 */
export async function constructGeometry(
    geomJson: Geometry | null | undefined,
    srWkid?: number,
): Promise<unknown> {
    if (!geomJson) return null;
    const sr =
        ("spatialReference" in geomJson && geomJson.spatialReference) ||
        (srWkid ? { wkid: srWkid } : { wkid: 4326 });

    if ("rings" in geomJson) {
        const Polygon = await $arcgis.import("esri/geometry/Polygon");
        return new Polygon({ rings: geomJson.rings, spatialReference: sr });
    }
    if ("paths" in geomJson) {
        const Polyline = await $arcgis.import("esri/geometry/Polyline");
        return new Polyline({ paths: geomJson.paths, spatialReference: sr });
    }
    if ("x" in geomJson && "y" in geomJson) {
        const Point = await $arcgis.import("esri/geometry/Point");
        return new Point({ x: geomJson.x, y: geomJson.y, spatialReference: sr });
    }
    return geomJson;
}
