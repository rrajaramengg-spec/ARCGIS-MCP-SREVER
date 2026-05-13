import { Button } from "@/components/Button";
import { useChatStore } from "@/stores/chat";
import { useCallback, useEffect, useRef, useState } from "react";
import { PICK_PIN_SYMBOL } from "./utils/symbols";

interface LocationPickerProps {
    getView: () => __esri.MapViewInstance | null;
    getModules: () => Record<string, unknown> | null;
    onPickModeChange?: (active: boolean) => void;
}

export function LocationPicker({ getView, getModules, onPickModeChange }: LocationPickerProps) {
    const [pickMode, setPickMode] = useState(false);
    const pickLayerRef = useRef<unknown>(null);
    const clickHandlerRef = useRef<{ remove: () => void } | null>(null);
    const appendInputText = useChatStore((s) => s.appendInputText);

    const togglePickMode = useCallback(() => {
        setPickMode((prev) => {
            const next = !prev;
            onPickModeChange?.(next);
            return next;
        });
    }, [onPickModeChange]);

    useEffect(() => {
        const view = getView();
        const modules = getModules();
        if (!view || !modules) return;


        const GraphicsLayer = modules.GraphicsLayer as new (...args: any[]) => any;

        const Graphic = modules.Graphic as new (...args: any[]) => any;

        if (pickMode) {
            // Create pick layer if needed
            if (!pickLayerRef.current) {
                pickLayerRef.current = new GraphicsLayer({
                    title: "Pick Location",
                    listMode: "hide",
                });
                (view as unknown as { map: { add: (l: unknown) => void } }).map.add(
                    pickLayerRef.current,
                );
            }

            const Point = modules.Point as new (...args: any[]) => unknown;

            // Register click handler
            const handler = (view as unknown as { on: (event: string, cb: (e: { stopPropagation: () => void; mapPoint: { longitude: number; latitude: number } }) => void) => { remove: () => void } }).on(
                "click",
                (event) => {
                    event.stopPropagation();
                    const lon = event.mapPoint.longitude.toFixed(4);
                    const lat = event.mapPoint.latitude.toFixed(4);
                    appendInputText(`${lon},${lat}`);

                    // Place temporary pin
                    const layer = pickLayerRef.current as { removeAll: () => void; add: (g: unknown) => void };
                    if (layer) {
                        layer.removeAll();
                        layer.add(
                            new Graphic({
                                geometry: new Point({
                                    longitude: Number(lon),
                                    latitude: Number(lat),
                                }),
                                symbol: PICK_PIN_SYMBOL,
                            }),
                        );
                    }
                },
            );
            clickHandlerRef.current = handler;
        } else {
            // Clean up
            if (clickHandlerRef.current) {
                clickHandlerRef.current.remove();
                clickHandlerRef.current = null;
            }
            if (pickLayerRef.current) {
                (pickLayerRef.current as { removeAll: () => void }).removeAll();
            }
        }

        return () => {
            if (clickHandlerRef.current) {
                clickHandlerRef.current.remove();
                clickHandlerRef.current = null;
            }
        };
    }, [pickMode, getView, getModules, appendInputText]);

    return (
        <Button
            variant="ghost"
            onClick={togglePickMode}
            className={pickMode ? "bg-accent/20" : ""}
            title="Pick location from map"
        >
            📍 {pickMode ? "Cancel" : "Pick"}
        </Button>
    );
}
