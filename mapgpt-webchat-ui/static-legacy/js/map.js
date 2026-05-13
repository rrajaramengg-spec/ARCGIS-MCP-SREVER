// ── Map Module — ArcGIS JS SDK 5.0 ──────────────
import {
    BASEMAP,
    BUFFER_SYMBOL,
    DEFAULT_CENTER, DEFAULT_ZOOM,
    LAYER_COLORS,
    LOCATE_SYMBOL,
    MAX_QUERY_LAYERS,
    PROXIMITY_LINE_SYMBOL,
    SOURCE_SYMBOL,
    buildParentSymbol,
    buildSymbol
} from './config.js';
import { normalizeQueryResponse } from './normalize.js';

let EsriMap, MapView, GraphicsLayer, Graphic, Point, Polygon, Polyline, SpatialReference;
let view = null;
const queryLayerMap = new Map();  // queryId → GraphicsLayer[]
let locateLayer = null;
let locatePoint = null; // Track last locate Point for zoomToLocate
let colorIndex = 0;     // Cycles through LAYER_COLORS

// ── Initialize MapView ──────────────────────────
export async function init() {
    const container = document.getElementById('map-container');

    // Show loading indicator while SDK loads
    if (container) {
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:14px;">Loading map\u2026</div>';
    }

    // Wait for ArcGIS SDK to be available (loaded via CDN module script)
    if (typeof $arcgis === 'undefined') {
        // Give the SDK a few seconds to load
        await new Promise((resolve, reject) => {
            let attempts = 0;
            const check = setInterval(() => {
                if (typeof $arcgis !== 'undefined') { clearInterval(check); resolve(); }
                else if (++attempts > 50) { clearInterval(check); reject(new Error('ArcGIS SDK not loaded')); }
            }, 200);
        });
    }

    try {
        [EsriMap, MapView, GraphicsLayer, Graphic, Point, Polygon, Polyline, SpatialReference] = await $arcgis.import([
            "@arcgis/core/Map.js",
            "@arcgis/core/views/MapView.js",
            "@arcgis/core/layers/GraphicsLayer.js",
            "@arcgis/core/Graphic.js",
            "@arcgis/core/geometry/Point.js",
            "@arcgis/core/geometry/Polygon.js",
            "@arcgis/core/geometry/Polyline.js",
            "@arcgis/core/geometry/SpatialReference.js"
        ]);

        const map = new EsriMap({ basemap: BASEMAP });

        // Clear loading placeholder before MapView takes over
        if (container) container.innerHTML = '';

        view = new MapView({
            container: 'map-container',
            map: map,
            center: DEFAULT_CENTER,
            zoom: DEFAULT_ZOOM
        });

        await view.when();
        _setupProximityHover();
        return view;
    } catch (err) {
        console.error('Map init failed:', err);
        const container = document.getElementById('map-container');
        if (container) {
            container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:14px;">Map unavailable — check network connection</div>';
        }
        throw err;
    }
}

// ── Add query results as GraphicsLayer(s) ────────
export async function addQueryLayer(data, queryText, queryId) {
    if (!view) return null;

    const normalized = normalizeQueryResponse(data);
    if (!normalized || normalized.layers.length === 0) return null;

    const MAX_FEATURES = 500;
    const createdLayers = [];
    let zoomTarget = null;

    for (const layerGroup of normalized.layers) {
        const isParent = layerGroup.role === 'parent';
        const geomType = mapGeometryType(layerGroup.geometryType);

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
            symbol = buildSymbol(geomType, LAYER_COLORS[colorIndex % LAYER_COLORS.length]);
            colorIndex++;
        }

        // Build popup template
        const popupTemplate = buildPopupTemplate(layerGroup);

        // Build title
        let title;
        if (isParent) {
            title = layerGroup.name || 'Boundary';
        } else {
            const countStr = layerGroup.count ? ` (${layerGroup.count.toLocaleString()} features)` : '';
            title = (layerGroup.name || queryText || `Query ${queryLayerMap.size + 1}`) + countStr;
        }

        // Cap features
        let features = layerGroup.features;
        if (features.length > MAX_FEATURES) {
            console.warn(`Rendering capped at ${MAX_FEATURES} of ${features.length} features for "${layerGroup.name}"`);
            title += ` (showing ${MAX_FEATURES} of ${features.length})`;
            features = features.slice(0, MAX_FEATURES);
        }

        // Create GraphicsLayer and add graphics in batches
        const graphicsLayer = new GraphicsLayer({ title });
        const srWkid = layerGroup.spatialReference?.wkid || 4326;

        await addGraphicsBatched(graphicsLayer, features, srWkid, symbol, popupTemplate);

        // Add distance labels for proximity lines at midpoint of each line
        if (layerGroup.proximityLines) {
            _addDistanceLabels(graphicsLayer, features, srWkid);
        }

        view.map.add(graphicsLayer);
        createdLayers.push(graphicsLayer);
        console.log(`[map] Added layer "${title}" — ${graphicsLayer.graphics.length} graphics`);

        // Track zoom target — prefer child/primary layers, fall back to parent
        if (!isParent && graphicsLayer.graphics.length > 0) {
            zoomTarget = graphicsLayer;
        } else if (isParent && !zoomTarget && graphicsLayer.graphics.length > 0) {
            zoomTarget = graphicsLayer;
        }
    }

    // Session history — store as group keyed by queryId
    if (queryId != null) {
        queryLayerMap.set(queryId, createdLayers);
        if (queryLayerMap.size > MAX_QUERY_LAYERS) {
            const oldestKey = queryLayerMap.keys().next().value;
            const oldest = queryLayerMap.get(oldestKey);
            oldest.forEach(l => view.map.remove(l));
            queryLayerMap.delete(oldestKey);
        }
    }

    // Zoom to child/primary layer
    if (zoomTarget) {
        await view.goTo(zoomTarget.graphics.toArray()).catch(() => { });
    }

    return createdLayers;
}

// ── Batched graphic construction ─────────────────
const BATCH_SIZE = 100;

async function addGraphicsBatched(graphicsLayer, features, srWkid, symbol, popupTemplate) {
    if (features.length <= BATCH_SIZE) {
        // Small set — process synchronously
        for (const f of features) {
            if (!f.geometry) continue;
            const geometry = constructGeometry(f.geometry, srWkid);
            if (!geometry) continue;
            const props = { geometry, attributes: f.attributes, symbol };
            if (popupTemplate) props.popupTemplate = popupTemplate;
            graphicsLayer.add(new Graphic(props));
        }
        return;
    }

    // Large set — process in batches with requestAnimationFrame yields
    let i = 0;
    while (i < features.length) {
        const end = Math.min(i + BATCH_SIZE, features.length);
        for (let j = i; j < end; j++) {
            const f = features[j];
            if (!f.geometry) continue;
            const geometry = constructGeometry(f.geometry, srWkid);
            if (!geometry) continue;
            const props = { geometry, attributes: f.attributes, symbol };
            if (popupTemplate) props.popupTemplate = popupTemplate;
            graphicsLayer.add(new Graphic(props));
        }
        i = end;
        if (i < features.length) {
            await new Promise(resolve => requestAnimationFrame(resolve));
        }
    }
}

// ── Build popup template from layer group ────────
function buildPopupTemplate(layerGroup) {
    // No popup for buffer zones
    if (layerGroup.bufferZone) return null;

    // Proximity lines: custom distance popup
    if (layerGroup.proximityLines) {
        return {
            title: 'Proximity Line',
            content: '<b>Distance:</b> {distance} {distance_unit}<br><b>Target ID:</b> {target_id}',
        };
    }

    const titleField = findTitleField(layerGroup);
    const title = titleField ? `{${titleField}}` : (layerGroup.name || 'Feature');

    // Use field metadata when available (standard FeatureSet with fields array)
    const fieldInfos = (layerGroup.fields || [])
        .filter(f => !['SHAPE', 'SHAPE_Length', 'SHAPE_Area'].includes(f.name))
        .map(f => ({ fieldName: f.name, label: f.alias || f.name }));

    if (fieldInfos.length > 0) {
        return { title, content: [{ type: 'fields', fieldInfos }] };
    }

    // Derive from first feature's attributes — use HTML template placeholders
    if (layerGroup.features?.length > 0) {
        const attrs = layerGroup.features[0]?.attributes;
        if (attrs) {
            const keys = Object.keys(attrs)
                .filter(k => !['SHAPE', 'SHAPE_Length', 'SHAPE_Area', 'OBJECTID', 'FID'].includes(k));
            if (keys.length > 0) {
                const rows = keys.map(k => `<b>${k}:</b> {${k}}`).join('<br>');
                return { title, content: rows };
            }
        }
    }

    // Fallback
    return { title, content: '{*}' };
}

// ── Add locate pin ───────────────────────────────
export async function addLocatePin(x, y, address) {
    if (!view) return;

    // Remove previous locate pin
    if (locateLayer) {
        view.map.remove(locateLayer);
    }

    const point = new Point({ longitude: x, latitude: y });
    locatePoint = point;

    const popupTemplate = {
        title: address || 'Located Address',
        content: `<b>Longitude:</b> ${x}<br><b>Latitude:</b> ${y}`,
    };

    const graphic = new Graphic({
        geometry: point,
        symbol: LOCATE_SYMBOL,
        popupTemplate: popupTemplate,
    });

    locateLayer = new GraphicsLayer({
        title: 'Locate Pin',
        graphics: [graphic],
    });

    view.map.add(locateLayer);
    await view.goTo({ target: point, scale: 5000 }).catch(() => { });
}

// ── Add buffer polygon layer ─────────────────────
export async function addBufferPolygonLayer(bufferGeometry, queryId) {
    if (!view || !bufferGeometry) return;

    const polygon = new Polygon({
        rings: bufferGeometry.rings,
        spatialReference: bufferGeometry.spatialReference || { wkid: 4326 },
    });

    const graphic = new Graphic({
        geometry: polygon,
        symbol: BUFFER_SYMBOL,
    });

    const layer = new GraphicsLayer({
        title: 'Buffer Zone',
        graphics: [graphic],
    });

    view.map.add(layer);

    // Register under the same queryId for cleanup
    if (queryId != null && queryLayerMap.has(queryId)) {
        queryLayerMap.get(queryId).push(layer);
    } else if (queryId != null) {
        queryLayerMap.set(queryId, [layer]);
    }
}

// ── Zoom to current locate pin ───────────────────
export function zoomToLocate() {
    if (!view || !locatePoint) return;
    view.goTo({ target: locatePoint, scale: 5000 }).catch(() => { });
}

// ── Zoom to query layer group by ID ─────────────────
export function zoomToQuery(queryId) {
    if (!view || queryLayerMap.size === 0) return;
    let group;
    if (queryId != null && queryLayerMap.has(queryId)) {
        group = queryLayerMap.get(queryId);
    } else {
        // Fallback to last entry
        group = [...queryLayerMap.values()].pop();
    }
    if (!group) return;
    // Find the child/primary layer in the group (not parent)
    const target = group.find(l => l.graphics.length > 0) || group[0];
    if (target && target.graphics.length > 0) {
        view.goTo(target.graphics.toArray()).catch(() => { });
    }
}

// ── Get MapView instance ─────────────────────────
export function getView() {
    return view;
}

// ── Clear all layers ─────────────────────────────
export function clearAllLayers() {
    if (!view) return;

    queryLayerMap.forEach(group => {
        group.forEach(layer => view.map.remove(layer));
    });
    queryLayerMap.clear();
    colorIndex = 0;

    if (locateLayer) {
        view.map.remove(locateLayer);
        locateLayer = null;
        locatePoint = null;
    }
}

// ── Smart popup title field selection ────────────
function findTitleField(layerGroup) {
    const fields = layerGroup.fields || [];

    // 1. Look for NAME field (case-insensitive)
    const nameField = fields.find(f => /^name$/i.test(f.name));
    if (nameField) return nameField.name;

    // 2. First string field
    const stringField = fields.find(f =>
        f.type === 'esriFieldTypeString' || f.type === 'string'
    );
    if (stringField) return stringField.name;

    // 3. displayFieldName
    if (layerGroup.displayFieldName) return layerGroup.displayFieldName;

    return null;
}

// ── Map geometry type string to SDK enum ─────────
function mapGeometryType(geomType) {
    if (!geomType) return 'point';
    const lower = geomType.toLowerCase();
    if (lower.includes('point') && lower.includes('multi')) return 'multipoint';
    if (lower.includes('point')) return 'point';
    if (lower.includes('polyline') || lower.includes('line')) return 'polyline';
    if (lower.includes('polygon')) return 'polygon';
    return 'point';
}

// ── Construct proper SDK geometry from REST JSON ─
function constructGeometry(geomJson, srWkid) {
    if (!geomJson) return null;
    const sr = geomJson.spatialReference || (srWkid ? { wkid: srWkid } : { wkid: 4326 });

    if (geomJson.rings) {
        return new Polygon({ rings: geomJson.rings, spatialReference: sr });
    }
    if (geomJson.paths) {
        return new Polyline({ paths: geomJson.paths, spatialReference: sr });
    }
    if (geomJson.x !== undefined && geomJson.y !== undefined) {
        return new Point({ x: geomJson.x, y: geomJson.y, spatialReference: sr });
    }
    // Fallback — let SDK try autocasting
    return geomJson;
}

// ── Distance labels for proximity lines ──────────
function _addDistanceLabels(graphicsLayer, features, srWkid) {
    for (const f of features) {
        const dist = f.attributes?.distance;
        if (dist == null || !f.geometry?.paths?.length) continue;
        const path = f.geometry.paths[0];
        if (!path || path.length < 2) continue;
        // Midpoint of the two-point line
        const mx = (path[0][0] + path[1][0]) / 2;
        const my = (path[0][1] + path[1][1]) / 2;
        const sr = f.geometry.spatialReference || (srWkid ? { wkid: srWkid } : { wkid: 4326 });
        const midpoint = new Point({ x: mx, y: my, spatialReference: sr });
        graphicsLayer.add(new Graphic({
            geometry: midpoint,
            symbol: {
                type: 'text',
                text: `${Math.round(dist)} ft`,
                color: '#333333',
                font: { size: 12 },
                haloColor: '#ffffff',
                haloSize: 2,
                yoffset: 8,
            },
        }));
    }
}

// ── Hover highlighting for proximity feature-line pairs ──
const HIGHLIGHT_SYMBOL_LINE = {
    type: 'simple-line',
    color: [255, 165, 0, 0.9],
    width: 3,
    style: 'solid',
};

let _highlightGraphic = null;

function _setupProximityHover() {
    if (!view) return;
    view.on('pointer-move', (event) => {
        // Remove previous highlight
        if (_highlightGraphic) {
            _highlightGraphic.layer?.remove(_highlightGraphic);
            _highlightGraphic = null;
        }
        view.hitTest(event).then((response) => {
            const hit = response.results?.find(r => r.graphic?.attributes?.target_id != null);
            if (!hit) return;
            const graphic = hit.graphic;
            const targetId = graphic.attributes.target_id;
            const layer = graphic.layer;
            if (!layer) return;

            // If user hovers a proximity line, highlight it
            if (graphic.geometry?.type === 'polyline') {
                _highlightGraphic = new Graphic({
                    geometry: graphic.geometry,
                    symbol: HIGHLIGHT_SYMBOL_LINE,
                });
                layer.add(_highlightGraphic);
            }
        }).catch(() => { });
    });
}
