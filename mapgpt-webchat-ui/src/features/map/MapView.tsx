import type { ExecuteResponse } from "@/types/api";
import { forwardRef, useImperativeHandle } from "react";
import { useGraphicsLayers } from "./hooks/useGraphicsLayers";
import { useMapView } from "./hooks/useMapView";

export interface MapViewRef {
    addQueryLayer: (data: ExecuteResponse | unknown, queryText: string, queryId: string) => Promise<unknown[] | null>;
    addLocatePin: (x: number, y: number, address?: string) => Promise<void>;
    clearAllLayers: () => void;
    zoomToLocate: () => void;
    zoomToQuery: (queryId: string) => void;
    getView: () => __esri.MapViewInstance | null;
    getModules: () => Record<string, unknown> | null;
    isReady: boolean;
}

export interface MapViewProps {
    pickMode?: boolean;
}

export const MapViewComponent = forwardRef<MapViewRef, MapViewProps>(function MapViewComponent({ pickMode }, ref) {
    const { containerRef, getView, getModules, isReady, error } = useMapView();
    const { addQueryLayer, addLocatePin, clearAllLayers, zoomToLocate, zoomToQuery } =
        useGraphicsLayers(getView, getModules);

    useImperativeHandle(
        ref,
        () => ({
            addQueryLayer,
            addLocatePin,
            clearAllLayers,
            zoomToLocate,
            zoomToQuery,
            getView,
            getModules,
            isReady,
        }),
        [addQueryLayer, addLocatePin, clearAllLayers, zoomToLocate, zoomToQuery, getView, getModules, isReady],
    );

    return (
        <div className="flex-1 w-full relative" style={{ minHeight: 0 }}>
            <div
                ref={containerRef}
                className="absolute inset-0"
                style={pickMode ? { cursor: "crosshair" } : undefined}
            />
            {error && (
                <div className="absolute inset-0 flex items-center justify-center text-error-fg text-sm pointer-events-none bg-error-bg/50">
                    Map failed to load: {error}
                </div>
            )}
            {!isReady && !error && (
                <div className="absolute inset-0 flex items-center justify-center text-muted text-sm pointer-events-none">
                    Loading map…
                </div>
            )}
        </div>
    );
});
