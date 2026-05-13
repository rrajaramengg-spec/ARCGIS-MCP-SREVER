import { Badge } from "@/components/Badge";
import type { LayerGroup } from "@/types/map";

const MAX_FEATURES = 500;

interface FeatureSummaryProps {
    layers: LayerGroup[];
}

function roleToBadgeColor(role: string) {
    switch (role) {
        case "parent":
            return "parent" as const;
        case "child":
            return "child" as const;
        case "buffer":
            return "buffer" as const;
        case "result":
            return "result" as const;
        default:
            return "primary" as const;
    }
}

export function FeatureSummary({ layers }: FeatureSummaryProps) {
    if (!layers || layers.length === 0) return null;

    const allZero = layers.every(
        (l) =>
            (l.count || 0) === 0 && (!l.features || l.features.length === 0),
    );
    if (allZero) {
        return (
            <div className="text-sm text-muted italic py-1">No features found</div>
        );
    }

    return (
        <div className="flex flex-wrap items-center gap-1.5 py-1">
            {layers.map((layer, i) => {
                const name = layer.name || layer.role || "Query";
                const count =
                    layer.count != null
                        ? layer.count
                        : layer.features
                            ? layer.features.length
                            : 0;

                // Buffer zone — show radius info
                if (
                    layer.bufferZone &&
                    layer.features &&
                    layer.features.length > 0
                ) {
                    const attrs = layer.features[0]?.attributes || {};
                    const radius = attrs.radius || "";
                    const unit = attrs.unit || "";
                    return (
                        <Badge key={i} color="parent">
                            {`Buffer: ${String(radius)} ${String(unit)}`}
                        </Badge>
                    );
                }

                let text = `${name}: ${count.toLocaleString()}`;
                if (count > MAX_FEATURES && layer.features && layer.features.length > 0) {
                    text += ` (showing ${MAX_FEATURES} on map)`;
                }
                if (layer.countOnly) {
                    text += " (count only)";
                }

                return (
                    <Badge key={i} color={roleToBadgeColor(layer.role || "primary")}>
                        {text}
                    </Badge>
                );
            })}
        </div>
    );
}
