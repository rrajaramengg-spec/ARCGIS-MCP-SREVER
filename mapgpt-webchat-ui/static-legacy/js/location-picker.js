// ── Location Picker Module — Map click-to-coordinate & Search widget ──
import { PICK_PIN_SYMBOL } from './config.js';

let view = null;
let appendInputText = null;
let pickMode = false;
let pickBtn = null;
let pickLayer = null;
let GraphicsLayer, Graphic, Point, Search;
let clickHandler = null;

// ── Initialize ──────────────────────────────────
export async function init(mapView, appendFn) {
    view = mapView;
    appendInputText = appendFn;
    if (!view) return;

    // Import ArcGIS SDK classes
    [GraphicsLayer, Graphic, Point, Search] = await $arcgis.import([
        "@arcgis/core/layers/GraphicsLayer.js",
        "@arcgis/core/Graphic.js",
        "@arcgis/core/geometry/Point.js",
        "@arcgis/core/widgets/Search.js"
    ]);

    // Create pick pin layer
    pickLayer = new GraphicsLayer({ title: 'Pick Location', listMode: 'hide' });
    view.map.add(pickLayer);

    // Wire pick button
    pickBtn = document.getElementById('pickLocationBtn');
    if (pickBtn) {
        pickBtn.onclick = () => togglePickMode();
    }

    // Add Search widget
    _initSearchWidget();

    console.log('[MapGPT] location-picker initialized');
}

// ── Toggle pick mode ────────────────────────────
export function togglePickMode() {
    pickMode = !pickMode;
    const container = document.getElementById('map-container');

    if (pickMode) {
        if (pickBtn) pickBtn.classList.add('active');
        if (container) container.classList.add('pick-mode');
        clickHandler = view.on('click', _onMapClick);
    } else {
        if (pickBtn) pickBtn.classList.remove('active');
        if (container) container.classList.remove('pick-mode');
        if (clickHandler) {
            clickHandler.remove();
            clickHandler = null;
        }
        // Remove temporary pin
        if (pickLayer) pickLayer.removeAll();
    }
}

// ── Map click handler ───────────────────────────
function _onMapClick(event) {
    // Don't capture clicks on UI widgets (e.g. Search widget)
    event.stopPropagation();

    const lon = event.mapPoint.longitude.toFixed(4);
    const lat = event.mapPoint.latitude.toFixed(4);
    const coordText = `${lon},${lat}`;

    // Append to chat input
    if (appendInputText) {
        appendInputText(coordText);
    }

    // Place/replace temporary pin
    if (pickLayer) {
        pickLayer.removeAll();
        pickLayer.add(new Graphic({
            geometry: new Point({
                longitude: event.mapPoint.longitude,
                latitude: event.mapPoint.latitude
            }),
            symbol: PICK_PIN_SYMBOL
        }));
    }
}

// ── Search widget ───────────────────────────────
function _initSearchWidget() {
    if (!Search || !view) return;

    const searchWidget = new Search({
        view,
        countryCode: 'US',
    });
    view.ui.add(searchWidget, 'top-right');

    searchWidget.on('select-result', (event) => {
        const name = event.result?.name;
        if (name && appendInputText) {
            appendInputText(name);
        }
    });
}
