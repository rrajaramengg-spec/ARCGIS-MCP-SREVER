/** Map symbol definitions — ported from static/js/config.js */

import type { EsriSymbol, SimpleFillSymbol, SimpleLineSymbol, SimpleMarkerSymbol } from "@/types/map";

/** Multi-color layer palette (cycles per query) */
export const LAYER_COLORS = [
    "#00897B", // Teal
    "#E64A19", // Deep Orange
    "#3949AB", // Indigo
    "#F9A825", // Amber
    "#8E24AA", // Purple
    "#00ACC1", // Cyan
];

const PARENT_STYLE = {
    fill: [100, 100, 100, 0.1] as number[],
    outline: "#666666",
    outlineWidth: 1.5,
    outlineStyle: "dash",
};

export function hexToRgba(hex: string, alpha: number): number[] {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b, alpha];
}

/** Build symbol for a geometry type with a given color. */
export function buildSymbol(geometryType: string | null, colorHex: string): EsriSymbol {
    const geom = (geometryType || "").toLowerCase();
    if (geom.includes("polyline") || geom.includes("line")) {
        return {
            type: "simple-line",
            color: hexToRgba(colorHex, 0.8),
            width: 2.5,
        };
    }
    if (geom.includes("polygon")) {
        return {
            type: "simple-fill",
            color: hexToRgba(colorHex, 0.25),
            outline: { color: hexToRgba(colorHex, 0.8), width: 1.5 },
        };
    }
    return {
        type: "simple-marker",
        color: hexToRgba(colorHex, 0.8),
        size: 8,
        outline: { color: [255, 255, 255], width: 1 },
    };
}

/** Build symbol for parent boundary layer (gray, dashed). */
export function buildParentSymbol(geometryType: string | null): EsriSymbol {
    const geom = (geometryType || "").toLowerCase();
    if (geom.includes("point")) {
        return {
            type: "simple-marker",
            color: PARENT_STYLE.fill,
            size: 8,
            outline: { color: PARENT_STYLE.outline, width: 1.5 },
        };
    }
    if (geom.includes("polyline") || geom.includes("line")) {
        return {
            type: "simple-line",
            color: PARENT_STYLE.fill,
            width: PARENT_STYLE.outlineWidth,
            style: PARENT_STYLE.outlineStyle,
        };
    }
    return {
        type: "simple-fill",
        color: PARENT_STYLE.fill,
        outline: {
            color: PARENT_STYLE.outline,
            width: PARENT_STYLE.outlineWidth,
            style: PARENT_STYLE.outlineStyle,
        },
    };
}

export const LOCATE_SYMBOL: SimpleMarkerSymbol = {
    type: "simple-marker",
    color: [211, 47, 47],
    size: 14,
    outline: { color: [255, 255, 255], width: 2 },
};

export const SOURCE_SYMBOL: SimpleMarkerSymbol = {
    type: "simple-marker",
    color: [33, 150, 243],
    size: 14,
    style: "diamond",
    outline: { color: [255, 255, 255], width: 2 },
};

export const BUFFER_SYMBOL: SimpleFillSymbol = {
    type: "simple-fill",
    color: [0, 150, 200, 0.08],
    outline: {
        color: [0, 150, 200, 0.6],
        width: 1.5,
        style: "dash",
    },
};

export const PROXIMITY_LINE_SYMBOL: SimpleLineSymbol = {
    type: "simple-line",
    color: [136, 136, 136, 0.7],
    width: 1.5,
    style: "dash",
};

export const PICK_PIN_SYMBOL: SimpleMarkerSymbol = {
    type: "simple-marker",
    color: [56, 168, 0],
    size: 12,
    outline: { color: [255, 255, 255], width: 2 },
};

export const PROXIMITY_HIGHLIGHT_SYMBOL: SimpleLineSymbol = {
    type: "simple-line",
    color: [255, 152, 0, 0.9],
    width: 3,
    style: "solid",
};

/** Factory for distance label text symbols placed at line midpoints. */
export function buildDistanceLabelSymbol(text: string): Record<string, unknown> {
    return {
        type: "text",
        text,
        color: [80, 80, 80],
        font: { size: 10, weight: "bold" },
        haloColor: [255, 255, 255],
        haloSize: 2,
        yoffset: 12,
    };
}
