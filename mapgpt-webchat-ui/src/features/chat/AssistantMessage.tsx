import { Button } from "@/components/Button";
import type { ExecuteResponse } from "@/types/api";
import type { ChatMessage } from "@/types/chat";
import type { NormalizedResponse } from "@/types/map";
import { normalizeQueryResponse } from "@/utils/normalize";
import { Code, GitBranch, Map, MapPin } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { ExecutionFlowModal } from "./ExecutionFlowModal";
import { FeatureSummary } from "./FeatureSummary";
import { FeatureTable } from "./FeatureTable";
import { FeedbackButtons } from "./FeedbackButtons";
import { MessageBubble } from "./MessageBubble";
import { RawResponseModal } from "./RawResponseModal";

interface AssistantMessageProps {
    message: ChatMessage;
    onZoomToQuery?: (queryId: string) => void;
    onZoomToLocate?: (x: number, y: number) => void;
}

export function AssistantMessage({
    message,
    onZoomToQuery,
    onZoomToLocate,
}: AssistantMessageProps) {
    const [rawModalOpen, setRawModalOpen] = useState(false);
    const [flowModalOpen, setFlowModalOpen] = useState(false);
    const rawData = message.rawData as ExecuteResponse | null;
    const action = rawData?.action;
    const queryId = message.queryId;

    // Normalize results for query/analyze/locate actions
    let normalized: NormalizedResponse | null = null;
    if (
        rawData &&
        (rawData.results || rawData.data) &&
        (action === "query" || action === "analyze" || action === "locate")
    ) {
        normalized =
            normalizeQueryResponse(rawData) ||
            (rawData.data ? normalizeQueryResponse(rawData.data as unknown as ExecuteResponse) : null);
    }

    // Locate coordinates
    let locateCoords: { x: number; y: number } | null = null;
    if (action === "locate" && rawData) {
        if (Array.isArray(rawData.results)) {
            const geo = rawData.results.find((r) => r.type === "geocode");
            if (geo && "location" in geo && geo.location) {
                locateCoords = geo.location;
            }
        }
        if (!locateCoords && rawData.data) {
            const d = rawData.data as Record<string, unknown>;
            const source = d.source as Record<string, unknown> | undefined;
            locateCoords =
                (source?.location as { x: number; y: number }) ||
                (d.location as { x: number; y: number }) ||
                ((d.candidates as Array<{ location: { x: number; y: number } }>)?.[0]
                    ?.location) ||
                null;
        }
    }

    // Show raw response link for data-bearing actions
    const showRawToggle =
        rawData &&
        (rawData.data || rawData.results) &&
        ["query", "search", "analyze", "locate"].includes(action || "");

    // Show map button when there are renderable features
    const hasRenderableFeatures =
        normalized?.layers.some(
            (l) => l.features && l.features.length > 0,
        ) ?? false;

    return (
        <MessageBubble role="assistant">
            {/* Markdown content */}
            <div className="prose prose-sm max-w-none dark:prose-invert">
                <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                    {message.text}
                </ReactMarkdown>
            </div>

            {/* Feature summary badges */}
            {normalized && <FeatureSummary layers={normalized.layers} />}

            {/* Feature tables */}
            {normalized &&
                (action === "query"
                    ? (() => {
                        const tableLayer =
                            normalized.layers.find((l) => l.role === "child") ||
                            normalized.layers[0];
                        return tableLayer?.features?.length ? (
                            <FeatureTable layer={tableLayer} />
                        ) : null;
                    })()
                    : normalized.layers
                        .filter(
                            (l) =>
                                l.role !== "parent" &&
                                !l.bufferZone &&
                                l.features &&
                                l.features.length > 0,
                        )
                        .map((layer, i) => <FeatureTable key={i} layer={layer} />))}

            {/* Action buttons */}
            <div className="flex flex-wrap gap-2 mt-1">
                {locateCoords && onZoomToLocate && (
                    <Button
                        variant="ghost"
                        onClick={() => onZoomToLocate(locateCoords!.x, locateCoords!.y)}
                    >
                        <MapPin size={16} className="inline mr-1" />
                        Zoom
                    </Button>
                )}
                {hasRenderableFeatures && queryId && onZoomToQuery && (
                    <Button variant="ghost" onClick={() => onZoomToQuery(queryId)}>
                        <Map size={16} className="inline mr-1" />
                        Show on Map
                    </Button>
                )}
            </div>

            {/* Raw response toggle */}
            {showRawToggle && (
                <div className="flex items-center gap-3 mt-1">
                    <button
                        className="flex items-center gap-1 text-xs text-muted hover:text-accent cursor-pointer bg-transparent border-none p-0"
                        onClick={() => setRawModalOpen(true)}
                    >
                        <Code size={14} />
                        View raw response
                    </button>
                    {rawData?.execution_graph?.node_timing && (
                        <button
                            className="flex items-center gap-1 text-xs text-muted hover:text-accent cursor-pointer bg-transparent border-none p-0"
                            onClick={() => setFlowModalOpen(true)}
                        >
                            <GitBranch size={14} />
                            Execution flow
                        </button>
                    )}
                </div>
            )}

            {/* Feedback buttons */}
            {queryId && rawData && (action as string) !== "error" && (
                <FeedbackButtons queryId={queryId} />
            )}

            {/* Raw response modal */}
            <RawResponseModal
                open={rawModalOpen}
                onClose={() => setRawModalOpen(false)}
                data={rawData}
            />

            {/* Execution flow modal */}
            <ExecutionFlowModal
                open={flowModalOpen}
                onClose={() => setFlowModalOpen(false)}
                graph={rawData?.execution_graph ?? null}
            />
        </MessageBubble>
    );
}
