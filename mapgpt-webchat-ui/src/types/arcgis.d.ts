/**
 * Thin type declarations for the ArcGIS JS SDK 5.0 loaded via CDN.
 * Only the ~8 classes actually used by this app are declared.
 * The CDN exposes `$arcgis.import()` as the module loader.
 */

 

interface ArcGISImporter {
    import(module: "esri/Map"): Promise<typeof __esri.MapConstructor>;
    import(module: "esri/views/MapView"): Promise<typeof __esri.MapViewConstructor>;
    import(
        module: "esri/layers/GraphicsLayer",
    ): Promise<typeof __esri.GraphicsLayerConstructor>;
    import(module: "esri/Graphic"): Promise<typeof __esri.GraphicConstructor>;
    import(module: "esri/geometry/Point"): Promise<typeof __esri.PointConstructor>;
    import(
        module: "esri/geometry/Polygon",
    ): Promise<typeof __esri.PolygonConstructor>;
    import(
        module: "esri/geometry/Polyline",
    ): Promise<typeof __esri.PolylineConstructor>;
    import(
        module: "esri/geometry/SpatialReference",
    ): Promise<typeof __esri.SpatialReferenceConstructor>;
    import(
        module: "esri/widgets/Search",
    ): Promise<typeof __esri.SearchConstructor>;
    import(module: string): Promise<any>;
}

declare const $arcgis: ArcGISImporter;

declare namespace __esri {
    interface MapConstructor {
        new(properties: { basemap: string }): MapInstance;
    }
    interface MapInstance {
        basemap: string;
        add(layer: any): void;
        remove(layer: any): void;
    }

    interface MapViewConstructor {
        new(properties: {
            container: HTMLElement;
            map: MapInstance;
            center?: [number, number];
            zoom?: number;
            scale?: number;
        }): MapViewInstance;
    }
    interface MapViewInstance {
        container: HTMLElement;
        map: MapInstance;
        center: any;
        zoom: number;
        scale: number;
        when(callback?: () => void): Promise<MapViewInstance>;
        goTo(target: any, options?: { animate?: boolean }): Promise<void>;
        destroy(): void;
        on(event: string, handler: (e: any) => void): { remove(): void };
        toMap(screenPoint: { x: number; y: number }): any;
        ui: { add(widget: any, position: string): void };
        graphics: { add(graphic: any): void; removeAll(): void };
    }

    interface GraphicsLayerConstructor {
        new(properties?: { id?: string; title?: string }): GraphicsLayerInstance;
    }
    interface GraphicsLayerInstance {
        id: string;
        title: string;
        graphics: { length: number; toArray(): any[] };
        add(graphic: any): void;
        addMany(graphics: any[]): void;
        removeAll(): void;
        fullExtent?: any;
    }

    interface GraphicConstructor {
        new(properties: {
            geometry: any;
            symbol?: any;
            attributes?: Record<string, unknown>;
            popupTemplate?: any;
        }): GraphicInstance;
    }
    interface GraphicInstance {
        geometry: any;
        symbol: any;
        attributes: Record<string, unknown>;
        popupTemplate: any;
    }

    interface PointConstructor {
        new(properties: {
            x: number;
            y: number;
            spatialReference?: any;
        }): PointInstance;
    }
    interface PointInstance {
        x: number;
        y: number;
        longitude: number;
        latitude: number;
        spatialReference: any;
    }

    interface PolygonConstructor {
        new(properties: { rings: number[][][]; spatialReference?: any }): any;
    }

    interface PolylineConstructor {
        new(properties: { paths: number[][][]; spatialReference?: any }): any;
    }

    interface SpatialReferenceConstructor {
        new(properties: { wkid: number }): any;
    }

    interface SearchConstructor {
        new(properties: { view: MapViewInstance;[key: string]: any }): any;
    }
}
