// ── GISChat Configuration Constants ───────────────

// Map defaults
export const BASEMAP = 'streets-navigation-vector';
export const DEFAULT_CENTER = [-98.5, 39.8];
export const DEFAULT_ZOOM = 4;

// Session map history
export const MAX_QUERY_LAYERS = 10;

// Multi-color layer palette (cycles per query)
export const LAYER_COLORS = [
    '#00897B', // Teal
    '#E64A19', // Deep Orange
    '#3949AB', // Indigo
    '#F9A825', // Amber
    '#8E24AA', // Purple
    '#00ACC1', // Cyan
];

// Parent boundary style (spatial join)
export const PARENT_STYLE = {
    fill: [100, 100, 100, 0.1],
    outline: '#666666',
    outlineWidth: 1.5,
    outlineStyle: 'dash',
};

// Convert hex color to RGBA array
function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b, alpha];
}

// Build symbol for a geometry type with a given color
export function buildSymbol(geometryType, colorHex) {
    const geom = (geometryType || '').toLowerCase();
    if (geom.includes('polyline') || geom.includes('line')) {
        return {
            type: 'simple-line',
            color: hexToRgba(colorHex, 0.8),
            width: 2.5,
        };
    }
    if (geom.includes('polygon')) {
        return {
            type: 'simple-fill',
            color: hexToRgba(colorHex, 0.25),
            outline: { color: hexToRgba(colorHex, 0.8), width: 1.5 },
        };
    }
    // point / multipoint / default
    return {
        type: 'simple-marker',
        color: hexToRgba(colorHex, 0.8),
        size: 8,
        outline: { color: [255, 255, 255], width: 1 },
    };
}

// Build symbol for parent boundary layer (gray, dashed for polygons/lines, gray marker for points)
export function buildParentSymbol(geometryType) {
    const geom = (geometryType || '').toLowerCase();
    if (geom.includes('point')) {
        return {
            type: 'simple-marker',
            color: PARENT_STYLE.fill,
            size: 8,
            outline: { color: PARENT_STYLE.outline, width: 1.5 },
        };
    }
    if (geom.includes('polyline') || geom.includes('line')) {
        return {
            type: 'simple-line',
            color: PARENT_STYLE.fill,
            width: PARENT_STYLE.outlineWidth,
            style: PARENT_STYLE.outlineStyle,
        };
    }
    // polygon / default
    return {
        type: 'simple-fill',
        color: PARENT_STYLE.fill,
        outline: {
            color: PARENT_STYLE.outline,
            width: PARENT_STYLE.outlineWidth,
            style: PARENT_STYLE.outlineStyle,
        },
    };
}

export const LOCATE_SYMBOL = {
    type: 'simple-marker',
    color: [211, 47, 47],
    size: 14,
    outline: { color: [255, 255, 255], width: 2 }
};

// Buffer zone symbol (semi-transparent cyan, dashed outline)
export const BUFFER_SYMBOL = {
    type: 'simple-fill',
    color: [0, 150, 200, 0.08],
    outline: {
        color: [0, 150, 200, 0.6],
        width: 1.5,
        style: 'dash',
    },
};

// API endpoints
export const WS_PATH = '/ws/chat';
export const API_COMMANDS = '/api/commands';
export const API_PROMPTS = '/api/prompts';
export const API_RESOURCES = '/api/resources';
