/** Popup template builder — ported from static/js/map.js */

import type { LayerGroup } from "@/types/map";

interface PopupTemplate {
    title: string;
    content: string | { type: string; fieldInfos: { fieldName: string; label: string }[] }[];
}

/** Find the best title field from a layer group's field metadata. */
export function findTitleField(layerGroup: LayerGroup): string | null {
    const fields = layerGroup.fields || [];

    // 1. NAME field (case-insensitive)
    const nameField = fields.find((f) => /^name$/i.test(f.name));
    if (nameField) return nameField.name;

    // 2. First string field
    const stringField = fields.find(
        (f) => f.type === "esriFieldTypeString" || f.type === "string",
    );
    if (stringField) return stringField.name;

    return null;
}

/** Build a popup template for a layer group. */
export function buildPopupTemplate(layerGroup: LayerGroup): PopupTemplate | null {
    if (layerGroup.bufferZone) return null;

    if (layerGroup.proximityLines) {
        return {
            title: "Proximity Line",
            content:
                "<b>Distance:</b> {distance} {distance_unit}<br><b>Target ID:</b> {target_id}",
        };
    }

    const titleField = findTitleField(layerGroup);
    const title = titleField
        ? `{${titleField}}`
        : layerGroup.name || "Feature";

    // Use field metadata when available
    const fieldInfos = (layerGroup.fields || [])
        .filter(
            (f) => !["SHAPE", "SHAPE_Length", "SHAPE_Area"].includes(f.name),
        )
        .map((f) => ({ fieldName: f.name, label: f.alias || f.name }));

    if (fieldInfos.length > 0) {
        return { title, content: [{ type: "fields", fieldInfos }] };
    }

    // Derive from first feature's attributes
    if (layerGroup.features?.length > 0) {
        const attrs = layerGroup.features[0]?.attributes;
        if (attrs) {
            const keys = Object.keys(attrs).filter(
                (k) =>
                    !["SHAPE", "SHAPE_Length", "SHAPE_Area", "OBJECTID", "FID"].includes(k),
            );
            if (keys.length > 0) {
                const rows = keys.map((k) => `<b>${k}:</b> {${k}}`).join("<br>");
                return { title, content: rows };
            }
        }
    }

    return { title, content: "{*}" };
}
