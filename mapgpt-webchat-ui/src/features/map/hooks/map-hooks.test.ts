import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGraphicsLayers } from "./useGraphicsLayers";

// Mock the ArcGIS-dependent modules
vi.mock("@/features/map/utils/geometry", () => ({
    constructGeometry: vi.fn().mockResolvedValue({ x: -75, y: 40 }),
    mapGeometryType: vi.fn().mockReturnValue("point"),
}));

vi.mock("@/features/map/utils/popup", () => ({
    buildPopupTemplate: vi.fn().mockReturnValue({ title: "Test" }),
    findTitleField: vi.fn(),
}));

function createMockModules() {
    return {
        GraphicsLayer: class {
            title = "";
            _graphicsList: unknown[] = [];
            graphics = {
                get length() {
                    return (this as unknown as { _parent: { _graphicsList: unknown[] } })._parent._graphicsList.length;
                },
                toArray: () => [] as unknown[],
                _parent: null as unknown,
            };
            constructor(opts?: { title?: string; graphics?: unknown[] }) {
                if (opts?.title) this.title = opts.title;
                if (opts?.graphics) this._graphicsList = [...opts.graphics];
                this.graphics._parent = this;
                this.graphics.toArray = () => [...this._graphicsList];
                // Fix the length getter
                // eslint-disable-next-line @typescript-eslint/no-this-alias
                const self = this;
                Object.defineProperty(this.graphics, "length", {
                    get() { return self._graphicsList.length; },
                });
            }
            add(g: unknown) { this._graphicsList.push(g); }
        },
        Graphic: class {
            geometry: unknown;
            attributes: unknown;
            symbol: unknown;
            constructor(props: Record<string, unknown>) {
                this.geometry = props.geometry;
                this.attributes = props.attributes;
                this.symbol = props.symbol;
            }
        },
        Point: class {
            longitude: number;
            latitude: number;
            constructor(p: { longitude: number; latitude: number }) {
                this.longitude = p.longitude;
                this.latitude = p.latitude;
            }
        },
        Polygon: class { },
        Polyline: class { },
        SpatialReference: class { },
        EsriMap: class { },
        MapView: class { },
    };
}

function createMockView() {
    const layers: unknown[] = [];
    return {
        map: {
            add: vi.fn((l: unknown) => layers.push(l)),
            remove: vi.fn((l: unknown) => {
                const idx = layers.indexOf(l);
                if (idx >= 0) layers.splice(idx, 1);
            }),
        },
        goTo: vi.fn().mockResolvedValue(undefined),
        on: vi.fn().mockReturnValue({ remove: vi.fn() }),
        hitTest: vi.fn().mockResolvedValue({ results: [] }),
        _layers: layers,
    };
}

describe("useGraphicsLayers", () => {
    let mockView: ReturnType<typeof createMockView>;
    let mockModules: ReturnType<typeof createMockModules>;

    beforeEach(() => {
        mockView = createMockView();
        mockModules = createMockModules();
    });

    it("addLocatePin adds a locate layer", async () => {
        const { result } = renderHook(() =>
            useGraphicsLayers(
                () => mockView as unknown as __esri.MapViewInstance,
                () => mockModules as unknown as Record<string, unknown>,
            ),
        );

        await act(async () => {
            await result.current.addLocatePin(-75, 40, "123 Main St");
        });

        expect(mockModules.Point).toBeDefined();
        expect(mockView.map.add).toHaveBeenCalled();
        expect(mockView.goTo).toHaveBeenCalled();
    });

    it("clearAllLayers removes all layers", async () => {
        const { result } = renderHook(() =>
            useGraphicsLayers(
                () => mockView as unknown as __esri.MapViewInstance,
                () => mockModules as unknown as Record<string, unknown>,
            ),
        );

        // Add a locate pin first
        await act(async () => {
            await result.current.addLocatePin(-75, 40);
        });

        act(() => {
            result.current.clearAllLayers();
        });

        expect(mockView.map.remove).toHaveBeenCalled();
    });

    it("addQueryLayer returns null when view is null", async () => {
        const { result } = renderHook(() =>
            useGraphicsLayers(
                () => null,
                () => null,
            ),
        );

        let res: unknown;
        await act(async () => {
            res = await result.current.addQueryLayer({}, "test", "q1");
        });
        expect(res).toBeNull();
    });

    it("zoomToLocate calls goTo when a locate point exists", async () => {
        const { result } = renderHook(() =>
            useGraphicsLayers(
                () => mockView as unknown as __esri.MapViewInstance,
                () => mockModules as unknown as Record<string, unknown>,
            ),
        );

        await act(async () => {
            await result.current.addLocatePin(-75, 40);
        });

        act(() => {
            result.current.zoomToLocate();
        });

        // goTo called once for addLocatePin, once for zoomToLocate
        expect(mockView.goTo).toHaveBeenCalledTimes(2);
    });

    it("zoomToQuery does nothing when no layers exist", () => {
        const { result } = renderHook(() =>
            useGraphicsLayers(
                () => mockView as unknown as __esri.MapViewInstance,
                () => mockModules as unknown as Record<string, unknown>,
            ),
        );

        act(() => {
            result.current.zoomToQuery("q1");
        });

        // goTo should not be called
        expect(mockView.goTo).not.toHaveBeenCalled();
    });
});
