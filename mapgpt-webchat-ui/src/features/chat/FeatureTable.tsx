import type { LayerGroup } from "@/types/map";

interface FeatureTableProps {
    layer: LayerGroup;
}

const SHAPE_FIELDS = ["SHAPE", "SHAPE_Length", "SHAPE_Area"];

export function FeatureTable({ layer }: FeatureTableProps) {
    if (!layer.features || layer.features.length === 0) return null;

    const totalCount = layer.count || layer.features.length;
    const displayFeatures = layer.features.slice(0, 10);
    const firstAttrs = displayFeatures[0]?.attributes;
    if (!firstAttrs) return null;

    const columns = Object.keys(firstAttrs).filter(
        (k) => !SHAPE_FIELDS.includes(k),
    );
    if (columns.length === 0) return null;

    // Build field alias map
    const fieldAliases: Record<string, string> = {};
    if (Array.isArray(layer.fields)) {
        layer.fields.forEach((f) => {
            if (f.name && f.alias) fieldAliases[f.name] = f.alias;
        });
    }

    // Metadata header
    const metaParts: string[] = [];
    if (layer.name) metaParts.push(layer.name);
    if (layer.geometryType) metaParts.push(layer.geometryType);
    if (layer.spatialReference?.wkid)
        metaParts.push("WKID: " + layer.spatialReference.wkid);
    metaParts.push(totalCount + " feature" + (totalCount !== 1 ? "s" : ""));

    return (
        <div className="my-2 border border-border rounded overflow-hidden text-xs">
            <div className="bg-surface px-3 py-1.5 text-muted font-medium">
                {metaParts.join(" · ")}
            </div>
            <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                    <thead>
                        <tr className="bg-bg">
                            {columns.map((col) => (
                                <th
                                    key={col}
                                    className="text-left px-2 py-1.5 border-b border-border font-medium text-text whitespace-nowrap"
                                >
                                    {fieldAliases[col] || col}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {displayFeatures.map((f, rowIdx) => (
                            <tr
                                key={rowIdx}
                                className="border-b border-border last:border-b-0 hover:bg-bg/50"
                            >
                                {columns.map((col) => {
                                    const val = f.attributes?.[col];
                                    return (
                                        <td
                                            key={col}
                                            className="px-2 py-1.5 whitespace-nowrap text-text"
                                        >
                                            {val != null ? String(val) : ""}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {totalCount > 10 && (
                <div className="px-3 py-1.5 text-muted text-center bg-surface">
                    Showing {displayFeatures.length} of {totalCount}
                </div>
            )}
        </div>
    );
}
