/** WebSocket message envelope types (server → client) */

/** Action types returned by the backend */
export type ActionType =
    | "query"
    | "locate"
    | "analyze"
    | "summarize"
    | "message"
    | "summarize-stat";

/** WebSocket message wrapper — discriminated on `type` */
export type WsMessage = WsResponse | WsProgress | WsError;

export interface WsResponse {
    type: "response";
    data: ExecuteResponse;
}

export interface WsProgress {
    type: "progress";
    data: { step: string };
}

export interface WsError {
    type: "error";
    data: { error: string };
}

/** The payload inside a "response" message — matches backend ExecuteResponse */
export interface ExecuteResponse {
    action: ActionType;
    message: string;
    data?: Record<string, unknown> | null;
    tool_name?: string | null;
    tool_args?: Record<string, unknown> | null;
    results?: ResultEntry[] | null;
    execution_time_ms?: number | null;
    timing?: TimingInfo | null;
    query_id?: string | null;
    execution_graph?: ExecutionGraph | null;
    error?: string;
}

/** Typed result entry — discriminated on `type` */
export type ResultEntry = FeatureSetResult | GeocodeResult;

export interface FeatureSetResult {
    type: "feature_set";
    layer?: string;
    layer_name?: string;
    layer_url?: string;
    features: Feature[];
    geometryType?: string | null;
    fields?: FieldInfo[];
    spatialReference?: SpatialReference | null;
    role?: string;
    count?: number;
}

export interface GeocodeResult {
    type: "geocode";
    location: { x: number; y: number };
    address?: string;
    score?: number;
    candidates?: GeocodeCandidate[];
}

export interface GeocodeCandidate {
    address: string;
    location: { x: number; y: number };
    score: number;
}

export interface Feature {
    geometry?: Geometry | null;
    attributes?: Record<string, unknown>;
}

export interface FieldInfo {
    name: string;
    alias?: string;
    type?: string;
}

export interface SpatialReference {
    wkid: number;
    latestWkid?: number;
}

export interface TimingInfo {
    rag_ms?: number;
    llm_ms?: number;
    tool_ms?: number;
    plan_ms?: number;
    graph_ms?: number;
    total_ms?: number;
}

export interface ExecutionGraph {
    nodes_executed?: number;
    parallel_groups?: number;
    retry_budget_used?: number;
    errors?: Record<string, unknown>;
    skipped?: string[];
    node_timing?: NodeTiming[];
    edges?: Array<{ source: string; target: string }>;
}

export interface NodeTiming {
    node_id: string;
    node_type?: string;
    ms: number;
    retries?: number;
    status?: string;
    depends_on?: string[];
    label?: string;
}

/** Outbound WebSocket payload (client → server) */
export interface WsSendPayload {
    message: string;
    session_id: string;
}

/** Geometry union — the backend sends ArcGIS-style geometry JSON */
export type Geometry = PointGeometry | PolylineGeometry | PolygonGeometry;

export interface PointGeometry {
    x: number;
    y: number;
    spatialReference?: SpatialReference;
}

export interface PolylineGeometry {
    paths: number[][][];
    spatialReference?: SpatialReference;
}

export interface PolygonGeometry {
    rings: number[][][];
    spatialReference?: SpatialReference;
}
