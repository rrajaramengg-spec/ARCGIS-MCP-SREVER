import { Button } from "@/components/Button";
import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from "react";
import { LocationPicker } from "./LocationPicker";
import { MapViewComponent, type MapViewRef } from "./MapView";

export type MapPanelRef = MapViewRef;

export const MapPanel = forwardRef<MapPanelRef>(function MapPanel(_, ref) {
    const mapRef = useRef<MapViewRef>(null);
    const [pickMode, setPickMode] = useState(false);

    const getView = useCallback(() => mapRef.current?.getView() ?? null, []);
    const getModules = useCallback(() => mapRef.current?.getModules() ?? null, []);

    useImperativeHandle(ref, () => ({
        addQueryLayer: (...args) => mapRef.current?.addQueryLayer(...args) ?? Promise.resolve(null),
        addLocatePin: (...args) => mapRef.current?.addLocatePin(...args) ?? Promise.resolve(),
        clearAllLayers: () => mapRef.current?.clearAllLayers(),
        zoomToLocate: () => mapRef.current?.zoomToLocate(),
        zoomToQuery: (...args) => mapRef.current?.zoomToQuery(...args),
        getView,
        getModules,
        get isReady() { return mapRef.current?.isReady ?? false; },
    }), [getView, getModules]);

    return (
        <div className="flex flex-col flex-1 overflow-hidden">
            {/* Header bar */}
            <div className="flex items-center justify-between px-3 py-1.5 bg-surface border-b border-border">
                <span className="text-sm font-medium text-text">Map</span>
                <div className="flex gap-2">
                    <LocationPicker getView={getView} getModules={getModules} onPickModeChange={setPickMode} />
                    <Button variant="ghost" onClick={() => mapRef.current?.clearAllLayers()}>
                        Clear Map
                    </Button>
                </div>
            </div>

            {/* Map container */}
            <MapViewComponent ref={mapRef} pickMode={pickMode} />
        </div>
    );
});
