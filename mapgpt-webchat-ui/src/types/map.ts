import type { Feature, FieldInfo, SpatialReference } from "./api";

/** Normalized layer group — the common shape consumed by map + chat rendering */
export interface LayerGroup {
    name: string;
    features: Feature[];
    geometryType: string | null;
    fields: FieldInfo[];
    spatialReference: SpatialReference | null;
    role: "child" | "parent" | "primary" | "result" | "buffer" | "distance_line" | "source";
    count: number;
    countOnly?: boolean;
    bufferZone?: boolean;
    proximityLines?: boolean;
    sourceLocation?: boolean;
    joinType?: string | null;
    totalInRadius?: number | null;
    searchRadius?: number | null;
    searchUnit?: string | null;
}

/** Normalized response — returned by normalizeQueryResponse */
export interface NormalizedResponse {
    layers: LayerGroup[];
    source?: Record<string, unknown>;
}

/** ArcGIS symbol type union */
export type EsriSymbol =
    | SimpleMarkerSymbol
    | SimpleLineSymbol
    | SimpleFillSymbol
    | TextSymbol;

export interface SimpleMarkerSymbol {
    type: "simple-marker";
    color: number[];
    size: number;
    style?: string;
    outline?: { color: number[] | string; width: number };
}

export interface SimpleLineSymbol {
    type: "simple-line";
    color: number[];
    width: number;
    style?: string;
}

export interface SimpleFillSymbol {
    type: "simple-fill";
    color: number[];
    outline?: {
        color: number[] | string;
        width: number;
        style?: string;
    };
}

export interface TextSymbol {
    type: "text";
    text: string;
    color: number[] | string;
    font?: { size: number; weight?: string };
    haloColor?: number[] | string;
    haloSize?: number;
}
