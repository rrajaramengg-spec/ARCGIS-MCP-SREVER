/**
 * Mock ArcGIS CDN classes for Vitest.
 * These replace the CDN-loaded `$arcgis.import()` classes in tests.
 */

 

/** Mock GraphicsLayer */
export class MockGraphicsLayer {
    id: string;
    title: string;
    graphics: { length: number; toArray: () => any[] };
    private _items: any[] = [];

    constructor(props?: { id?: string; title?: string }) {
        this.id = props?.id ?? "";
        this.title = props?.title ?? "";
        this.graphics = {
            get length() {
                return 0;
            },
            toArray: () => [],
        };
    }

    add(g: any) {
        this._items.push(g);
        this.graphics = {
            length: this._items.length,
            toArray: () => [...this._items],
        };
    }
    addMany(gs: any[]) {
        gs.forEach((g) => this.add(g));
    }
    removeAll() {
        this._items = [];
        this.graphics = { length: 0, toArray: () => [] };
    }
}

/** Mock Graphic */
export class MockGraphic {
    geometry: any;
    symbol: any;
    attributes: Record<string, unknown>;
    popupTemplate: any;

    constructor(props: {
        geometry?: any;
        symbol?: any;
        attributes?: Record<string, unknown>;
        popupTemplate?: any;
    }) {
        this.geometry = props.geometry ?? null;
        this.symbol = props.symbol ?? null;
        this.attributes = props.attributes ?? {};
        this.popupTemplate = props.popupTemplate ?? null;
    }
}

/** Mock Point */
export class MockPoint {
    x: number;
    y: number;
    longitude: number;
    latitude: number;
    spatialReference: any;

    constructor(props: { x: number; y: number; spatialReference?: any }) {
        this.x = props.x;
        this.y = props.y;
        this.longitude = props.x;
        this.latitude = props.y;
        this.spatialReference = props.spatialReference ?? { wkid: 4326 };
    }
}

/** Mock Polygon */
export class MockPolygon {
    rings: number[][][];
    spatialReference: any;

    constructor(props: { rings: number[][][]; spatialReference?: any }) {
        this.rings = props.rings;
        this.spatialReference = props.spatialReference ?? { wkid: 4326 };
    }
}

/** Mock Polyline */
export class MockPolyline {
    paths: number[][][];
    spatialReference: any;

    constructor(props: { paths: number[][][]; spatialReference?: any }) {
        this.paths = props.paths;
        this.spatialReference = props.spatialReference ?? { wkid: 4326 };
    }
}

/** Mock SpatialReference */
export class MockSpatialReference {
    wkid: number;
    constructor(props: { wkid: number }) {
        this.wkid = props.wkid;
    }
}

/** Mock Map */
export class MockMap {
    basemap: string;
    private _layers: any[] = [];

    constructor(props: { basemap: string }) {
        this.basemap = props.basemap;
    }
    add(layer: any) {
        this._layers.push(layer);
    }
    remove(layer: any) {
        this._layers = this._layers.filter((l) => l !== layer);
    }
}

/** Mock MapView */
export class MockMapView {
    container: HTMLElement | null;
    map: any;
    center: any;
    zoom: number;
    scale: number;
    ui = {
        add: (_widget: any, _position: string) => { },
    };
    graphics = {
        add: (_g: any) => { },
        removeAll: () => { },
    };

    constructor(props: {
        container?: HTMLElement;
        map?: any;
        center?: [number, number];
        zoom?: number;
        scale?: number;
    }) {
        this.container = props.container ?? null;
        this.map = props.map ?? null;
        this.center = props.center ?? [0, 0];
        this.zoom = props.zoom ?? 4;
        this.scale = props.scale ?? 0;
    }

    async when() {
        return this;
    }
    async goTo(_target: any, _opts?: any) { }
    destroy() {
        this.container = null;
    }
    on(_event: string, _handler: (e: any) => void) {
        return { remove: () => { } };
    }
    toMap(screenPoint: { x: number; y: number }) {
        return { longitude: screenPoint.x, latitude: screenPoint.y };
    }
}

/** Mock Search widget */
export class MockSearch {
    view: any;
    constructor(props: { view: any;[key: string]: any }) {
        this.view = props.view;
    }
}

/**
 * Mock `$arcgis.import()` — resolves to the corresponding mock class.
 */
export const mockModules: Record<string, any> = {
    "esri/Map": MockMap,
    "esri/views/MapView": MockMapView,
    "esri/layers/GraphicsLayer": MockGraphicsLayer,
    "esri/Graphic": MockGraphic,
    "esri/geometry/Point": MockPoint,
    "esri/geometry/Polygon": MockPolygon,
    "esri/geometry/Polyline": MockPolyline,
    "esri/geometry/SpatialReference": MockSpatialReference,
    "esri/widgets/Search": MockSearch,
};

/** Mock $arcgis global for test setup */
export function setupArcGISMock(): void {
    (globalThis as any).$arcgis = {
        import: async (modules: string | string[]) => {
            if (Array.isArray(modules)) {
                return modules.map((m) => mockModules[m] ?? {});
            }
            return mockModules[modules] ?? {};
        },
    };
}

/** Teardown the mock */
export function teardownArcGISMock(): void {
    delete (globalThis as any).$arcgis;
}
