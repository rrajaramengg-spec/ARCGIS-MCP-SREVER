import {
    BASEMAP,
    DEFAULT_CENTER,
    DEFAULT_ZOOM,
} from "@/features/map/utils/constants";
import { useChatStore } from "@/stores/chat";
import { useCallback, useEffect, useRef, useState } from "react";

/** ArcGIS class references loaded from CDN. */
export interface ArcGISModules {
    [key: string]: unknown;
    EsriMap: unknown;
    MapView: unknown;
    GraphicsLayer: unknown;
    Graphic: unknown;
    Point: unknown;
    Polygon: unknown;
    Polyline: unknown;
    SpatialReference: unknown;
}

export interface MapViewHandle {
    view: __esri.MapViewInstance | null;
    modules: ArcGISModules | null;
    isReady: boolean;
}

/**
 * Manages ArcGIS MapView lifecycle — creates on mount, destroys on unmount.
 * Returns a ref to the container div and the view handle.
 */
export function useMapView() {
    const containerRef = useRef<HTMLDivElement>(null);
    const viewRef = useRef<__esri.MapViewInstance | null>(null);
    const modulesRef = useRef<ArcGISModules | null>(null);
    const searchRef = useRef<unknown>(null);
    const [isReady, setIsReady] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let destroyed = false;

        async function initMap() {
            if (!containerRef.current) return;

            // Dynamically load ArcGIS SDK if not already present
            if (typeof $arcgis === "undefined") {
                // Check if script tag already added by another instance
                if (!document.querySelector('script[src*="js.arcgis.com/5.0"]')) {
                    const script = document.createElement("script");
                    script.type = "module";
                    script.src = "https://js.arcgis.com/5.0/";
                    document.head.appendChild(script);
                }

                await new Promise<void>((resolve, reject) => {
                    let attempts = 0;
                    const check = setInterval(() => {
                        if (typeof $arcgis !== "undefined") {
                            clearInterval(check);
                            resolve();
                        } else if (++attempts > 50) {
                            clearInterval(check);
                            reject(new Error("ArcGIS SDK not loaded"));
                        }
                    }, 200);
                });
            }

            const [
                EsriMap,
                MapView,
                GraphicsLayer,
                Graphic,
                Point,
                Polygon,
                Polyline,
                SpatialReference,
                Search,
            ] = await ($arcgis as unknown as { import: (modules: string[]) => Promise<unknown[]> }).import([
                "@arcgis/core/Map.js",
                "@arcgis/core/views/MapView.js",
                "@arcgis/core/layers/GraphicsLayer.js",
                "@arcgis/core/Graphic.js",
                "@arcgis/core/geometry/Point.js",
                "@arcgis/core/geometry/Polygon.js",
                "@arcgis/core/geometry/Polyline.js",
                "@arcgis/core/geometry/SpatialReference.js",
                "@arcgis/core/widgets/Search.js",
            ]);

            if (destroyed) return;

            modulesRef.current = {
                EsriMap,
                MapView,
                GraphicsLayer,
                Graphic,
                Point,
                Polygon,
                Polyline,
                SpatialReference,
            };

            const MapClass = EsriMap as new (opts: { basemap: string }) => unknown;
            const ViewClass = MapView as new (opts: {
                container: HTMLDivElement;
                map: unknown;
                center: [number, number];
                zoom: number;
            }) => __esri.MapViewInstance;

            const map = new MapClass({ basemap: BASEMAP });
            const view = new ViewClass({
                container: containerRef.current!,
                map,
                center: DEFAULT_CENTER as [number, number],
                zoom: DEFAULT_ZOOM,
            });

            viewRef.current = view;
            await (view as unknown as { when: () => Promise<void> }).when();

            if (!destroyed) {
                // Add Search widget
                const SearchClass = Search as new (opts: { view: unknown }) => unknown;
                const searchWidget = new SearchClass({ view });
                (view as unknown as { ui: { add: (w: unknown, pos: string) => void } }).ui.add(searchWidget, "top-right");
                (searchWidget as unknown as { on: (event: string, cb: (evt: unknown) => void) => void }).on("select-result", (evt: unknown) => {
                    const result = (evt as { result?: { name?: string } })?.result;
                    if (result?.name) {
                        useChatStore.getState().appendInputText(result.name);
                    }
                });
                searchRef.current = searchWidget;

                setIsReady(true);
            }
        }

        initMap().catch((err) => {
            console.error("Map init failed:", err);
            if (!destroyed) setError(String(err?.message ?? err));
        });

        return () => {
            destroyed = true;
            if (searchRef.current) {
                (searchRef.current as { destroy?: () => void }).destroy?.();
                searchRef.current = null;
            }
            if (viewRef.current) {
                (viewRef.current as unknown as { destroy: () => void }).destroy();
                viewRef.current = null;
            }
            setIsReady(false);
        };
    }, []);

    const getView = useCallback(() => viewRef.current, []);
    const getModules = useCallback(() => modulesRef.current, []);

    return { containerRef, getView, getModules, isReady, error };
}
