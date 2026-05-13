import { MAX_QUERY_LAYERS } from "@/features/map/utils/constants";
import { constructGeometry, mapGeometryType } from "@/features/map/utils/geometry";
import { buildPopupTemplate } from "@/features/map/utils/popup";
import {
    BUFFER_SYMBOL,
    LAYER_COLORS,
    LOCATE_SYMBOL,
    PROXIMITY_HIGHLIGHT_SYMBOL,
    PROXIMITY_LINE_SYMBOL,
    SOURCE_SYMBOL,
    buildDistanceLabelSymbol,
    buildParentSymbol,
    buildSymbol,
} from "@/features/map/utils/symbols";
import type { ExecuteResponse } from "@/types/api";
import { normalizeQueryResponse } from "@/utils/normalize";
import { useCallback, useEffect, useRef } from "react";

const MAX_FEATURES = 2000;
const BATCH_SIZE = 100;


type AnyConstructor = new (...args: any[]) => any;

/** Yield to the browser between batches for large feature sets. */
function rafYield(): Promise<void> {
    return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

/**
 * Manages query graphics layers, color cycling, layer cleanup,
 * addQueryLayer, addLocatePin, clearAllLayers, zoomToLocate, zoomToQuery.
 */
export function useGraphicsLayers(
    getView: () => __esri.MapViewInstance | null,
    getModules: () => Record<string, unknown> | null,
) {
    const queryLayerMapRef = useRef(new Map<string, unknown[]>());
    const locateLayerRef = useRef<unknown>(null);
    const locatePointRef = useRef<unknown>(null);
    const colorIndexRef = useRef(0);
    const renderGenRef = useRef(0);
    const hoverHandlerRef = useRef<{ remove: () => void } | null>(null);
    const highlightLayerRef = useRef<unknown>(null);

    const addQueryLayer = useCallback(
        async (data: ExecuteResponse | unknown, queryText: string, queryId: string) => {
            const view = getView();
            const modules = getModules();
            if (!view || !modules) return null;

            const normalized = normalizeQueryResponse(data as ExecuteResponse);
            if (!normalized || normalized.layers.length === 0) return null;

            const GraphicsLayer = modules.GraphicsLayer as AnyConstructor;
            const Graphic = modules.Graphic as AnyConstructor;

            const createdLayers: unknown[] = [];
            let zoomTarget: { graphics: { length: number; toArray: () => unknown[] } } | null = null;

            for (const layerGroup of normalized.layers) {
                const isParent = layerGroup.role === "parent";
                const geomType = mapGeometryType(layerGroup.geometryType || null);

                // Choose symbol
                let symbol;
                if (layerGroup.bufferZone) {
                    symbol = BUFFER_SYMBOL;
                } else if (layerGroup.proximityLines) {
                    symbol = PROXIMITY_LINE_SYMBOL;
                } else if (layerGroup.sourceLocation) {
                    symbol = SOURCE_SYMBOL;
                } else if (isParent) {
                    symbol = buildParentSymbol(geomType);
                } else {
                    symbol = buildSymbol(
                        geomType,
                        LAYER_COLORS[colorIndexRef.current % LAYER_COLORS.length],
                    );
                    colorIndexRef.current++;
                }

                const popupTemplate = buildPopupTemplate(layerGroup);

                // Build title
                let title: string;
                if (isParent) {
                    title = layerGroup.name || "Boundary";
                } else {
                    const countStr = layerGroup.count
                        ? ` (${layerGroup.count.toLocaleString()} features)`
                        : "";
                    title =
                        (layerGroup.name ||
                            queryText ||
                            `Query ${queryLayerMapRef.current.size + 1}`) + countStr;
                }

                // Cap features
                let features = layerGroup.features || [];
                if (features.length > MAX_FEATURES) {
                    title += ` (showing ${MAX_FEATURES} of ${features.length})`;
                    features = features.slice(0, MAX_FEATURES);
                }

                const graphicsLayer = new GraphicsLayer({ title });
                const srWkid = layerGroup.spatialReference?.wkid || 4326;
                const currentGen = ++renderGenRef.current;

                // Add graphics — batch for large feature sets
                if (features.length > BATCH_SIZE) {
                    for (let i = 0; i < features.length; i++) {
                        if (renderGenRef.current !== currentGen) break;
                        const f = features[i];
                        if (!f.geometry) continue;
                        const geometry = await constructGeometry(f.geometry, srWkid);
                        if (!geometry) continue;
                        const props: Record<string, unknown> = {
                            geometry,
                            attributes: f.attributes,
                            symbol,
                        };
                        if (popupTemplate) props.popupTemplate = popupTemplate;
                        graphicsLayer.add(new Graphic(props));
                        if ((i + 1) % BATCH_SIZE === 0) await rafYield();
                    }
                } else {
                    for (const f of features) {
                        if (!f.geometry) continue;
                        const geometry = await constructGeometry(f.geometry, srWkid);
                        if (!geometry) continue;
                        const props: Record<string, unknown> = {
                            geometry,
                            attributes: f.attributes,
                            symbol,
                        };
                        if (popupTemplate) props.popupTemplate = popupTemplate;
                        graphicsLayer.add(new Graphic(props));
                    }
                }

                // Add distance labels at proximity line target endpoints
                if (layerGroup.proximityLines && features.length > 0) {
                    for (const f of features) {
                        const paths = (f.geometry as unknown as { paths?: number[][][] })?.paths;
                        const dist = f.attributes?.distance;
                        if (!paths || !dist) continue;
                        const firstPath = paths[0];
                        if (!firstPath || firstPath.length < 2) continue;
                        // Use the last point (target end) so label appears above target graphic
                        const targetPt = firstPath[firstPath.length - 1];
                        if (!targetPt) continue;
                        const distUnit = f.attributes?.distance_unit || "ft";
                        const labelText = typeof dist === "number" ? `${dist.toFixed(1)} ${distUnit}` : String(dist);
                        graphicsLayer.add(new Graphic({
                            geometry: { type: "point", longitude: targetPt[0], latitude: targetPt[1] },
                            symbol: buildDistanceLabelSymbol(labelText),
                        }));
                    }
                }

                (view as unknown as { map: { add: (l: unknown) => void } }).map.add(
                    graphicsLayer,
                );
                createdLayers.push(graphicsLayer);

                if (!isParent && graphicsLayer.graphics.length > 0) {
                    zoomTarget = graphicsLayer;
                } else if (isParent && !zoomTarget && graphicsLayer.graphics.length > 0) {
                    zoomTarget = graphicsLayer;
                }
            }

            // Store layers by queryId
            queryLayerMapRef.current.set(queryId, createdLayers);
            if (queryLayerMapRef.current.size > MAX_QUERY_LAYERS) {
                const oldestKey = queryLayerMapRef.current.keys().next().value!;
                const oldest = queryLayerMapRef.current.get(oldestKey) as unknown[];
                oldest.forEach((l) =>
                    (view as unknown as { map: { remove: (l: unknown) => void } }).map.remove(l),
                );
                queryLayerMapRef.current.delete(oldestKey);
            }

            // Zoom to results
            if (zoomTarget) {
                await (view as unknown as { goTo: (t: unknown) => Promise<void> })
                    .goTo(zoomTarget.graphics.toArray())
                    .catch(() => { });
            }

            return createdLayers;
        },
        [getView, getModules],
    );

    const addLocatePin = useCallback(
        async (x: number, y: number, address?: string) => {
            const view = getView();
            const modules = getModules();
            if (!view || !modules) return;

            const Point = modules.Point as AnyConstructor;
            const Graphic = modules.Graphic as AnyConstructor;
            const GraphicsLayer = modules.GraphicsLayer as AnyConstructor;
            const mapObj = (view as unknown as { map: { remove: (l: unknown) => void; add: (l: unknown) => void } }).map;

            // Remove previous locate pin
            if (locateLayerRef.current) {
                mapObj.remove(locateLayerRef.current);
            }

            const point = new Point({ longitude: x, latitude: y });
            locatePointRef.current = point;

            const graphic = new Graphic({
                geometry: point,
                symbol: LOCATE_SYMBOL,
                popupTemplate: {
                    title: address || "Located Address",
                    content: `<b>Longitude:</b> ${x}<br><b>Latitude:</b> ${y}`,
                },
            });

            const layer = new GraphicsLayer({
                title: "Locate Pin",
                graphics: [graphic],
            });

            locateLayerRef.current = layer;
            mapObj.add(layer);

            await (view as unknown as { goTo: (t: { target: unknown; scale: number }) => Promise<void> })
                .goTo({ target: point, scale: 5000 })
                .catch(() => { });
        },
        [getView, getModules],
    );

    const clearAllLayers = useCallback(() => {
        const view = getView();
        if (!view) return;
        const mapObj = (view as unknown as { map: { remove: (l: unknown) => void } }).map;

        queryLayerMapRef.current.forEach((group) => {
            (group as unknown[]).forEach((layer) => mapObj.remove(layer));
        });
        queryLayerMapRef.current.clear();
        colorIndexRef.current = 0;

        if (locateLayerRef.current) {
            mapObj.remove(locateLayerRef.current);
            locateLayerRef.current = null;
            locatePointRef.current = null;
        }
    }, [getView]);

    const zoomToLocate = useCallback(() => {
        const view = getView();
        if (!view || !locatePointRef.current) return;
        (view as unknown as { goTo: (t: { target: unknown; scale: number }) => Promise<void> })
            .goTo({ target: locatePointRef.current, scale: 5000 })
            .catch(() => { });
    }, [getView]);

    const zoomToQuery = useCallback(
        (queryId: string) => {
            const view = getView();
            if (!view || queryLayerMapRef.current.size === 0) return;

            let group: unknown[] | undefined;
            if (queryLayerMapRef.current.has(queryId)) {
                group = queryLayerMapRef.current.get(queryId) as unknown[];
            } else {
                group = [...queryLayerMapRef.current.values()].pop() as unknown[];
            }
            if (!group) return;

            const target = group.find(
                (l) => (l as { graphics: { length: number } }).graphics.length > 0,
            ) || group[0];
            if (target) {
                const graphics = (target as { graphics: { toArray: () => unknown[] } }).graphics;
                if (graphics.toArray) {
                    (view as unknown as { goTo: (t: unknown) => Promise<void> })
                        .goTo(graphics.toArray())
                        .catch(() => { });
                }
            }
        },
        [getView],
    );

    // Proximity line hover highlight
    useEffect(() => {
        const view = getView();
        const modules = getModules();
        if (!view || !modules) return;

        const GraphicsLayer = modules.GraphicsLayer as AnyConstructor;
        const Graphic = modules.Graphic as AnyConstructor;

        const hlLayer = new GraphicsLayer({ title: "_proximity_highlight", listMode: "hide" });
        (view as unknown as { map: { add: (l: unknown) => void } }).map.add(hlLayer);
        highlightLayerRef.current = hlLayer;

        let throttled = false;
        const handler = (view as unknown as { on: (event: string, cb: (e: { x: number; y: number }) => void) => { remove: () => void } }).on(
            "pointer-move",
            (evt) => {
                if (throttled) return;
                throttled = true;
                setTimeout(() => { throttled = false; }, 50);

                (view as unknown as { hitTest: (p: { x: number; y: number }) => Promise<{ results: Array<{ graphic: { geometry?: { type?: string }; symbol?: { type?: string }; clone: () => unknown } }> }> }).hitTest(evt).then((response) => {
                    (hlLayer as { removeAll: () => void }).removeAll();
                    const hit = response.results.find(
                        (r) => r.graphic?.geometry?.type === "polyline" && r.graphic?.symbol?.type === "simple-line",
                    );
                    if (hit) {
                        (hlLayer as { add: (g: unknown) => void }).add(
                            new Graphic({
                                geometry: (hit.graphic as unknown as { geometry: unknown }).geometry,
                                symbol: PROXIMITY_HIGHLIGHT_SYMBOL,
                            }),
                        );
                    }
                }).catch(() => { /* ignore hit test failures */ });
            },
        );
        hoverHandlerRef.current = handler;

        return () => {
            handler.remove();
            hoverHandlerRef.current = null;
            (view as unknown as { map: { remove: (l: unknown) => void } }).map.remove(hlLayer);
            highlightLayerRef.current = null;
        };
    }, [getView, getModules]);

    return {
        addQueryLayer,
        addLocatePin,
        clearAllLayers,
        zoomToLocate,
        zoomToQuery,
    };
}
