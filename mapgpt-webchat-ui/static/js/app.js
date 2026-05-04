// ── App Orchestrator — Entry Point ────────────────
import * as api from './api.js';
import * as chat from './chat.js';
import * as map from './map.js';

console.log('[GISChat] app.js module loaded');

let mapReady = false;
let queryIdCounter = 0;

document.addEventListener('DOMContentLoaded', async () => {
    console.log('[GISChat] DOMContentLoaded fired');

    // ── Initialize chat UI ───────────────────────
    chat.init(sendMessage);
    console.log('[GISChat] chat.init() done');

    // ── Wire API log/status callbacks to chat ────
    api.onLog((level, text) => chat.addLog(level, text));
    api.onStatus((state) => {
        console.log('[GISChat] status:', state);
        chat.updateStatus(state);
    });

    // ── Wire WebSocket message handler ───────────
    api.onMessage(handleMessage);

    // ── Connect WebSocket ────────────────────────
    console.log('[GISChat] calling api.connect()');
    api.connect();

    // ── Display session ID indicator ─────────────
    const sid = api.getSessionId();
    if (sid) {
        const indicator = document.getElementById('sessionIndicator');
        if (indicator) {
            indicator.textContent = `Session: ${sid.substring(0, 8)}…`;
        }
    }

    // ── Wire panel min/max buttons ───────────────
    wireMinMaxButtons();

    // ── Wire Clear Map button ────────────────────
    const clearMapBtn = document.getElementById('clearMapBtn');
    if (clearMapBtn) {
        clearMapBtn.onclick = () => map.clearAllLayers();
    }

    // ── Initialize map (non-blocking — don't delay chat) ─
    map.init().then(() => {
        mapReady = true;
        console.log('[GISChat] map ready');
    }).catch(err => {
        console.warn('[GISChat] Map initialization failed:', err);
        chat.addLog('warn', 'Map unavailable — chat-only mode');
    });
});

// ── Send message flow ────────────────────────────
function sendMessage() {
    const text = chat.getInputText();
    if (!text || !api.isConnected()) return;

    chat.addUserMessage(text);
    chat.clearInput();
    chat.disableSend();
    chat.showThinking();
    api.send(text);
}

// ── Handle incoming WebSocket messages ───────────
function handleMessage(msg) {
    chat.hideThinking();

    if (msg.type === 'error') {
        const errText = msg.data?.error || 'An unexpected error occurred';
        chat.addErrorMessage(errText);
        chat.enableSend();
        return;
    }

    if (msg.type === 'progress') {
        chat.showProgress(msg.data?.step || '');
        return;
    }

    if (msg.type === 'response') {
        const data = msg.data;
        chat.addLog('info', `Response keys: ${Object.keys(data).join(', ')}`);

        // Handle errors — check for 'error' key presence (not just truthiness)
        // to catch empty-string errors from backend timeouts
        if ('error' in data) {
            const errText = data.error || 'An unexpected error occurred';
            chat.addErrorMessage(`Error: ${errText}`);
            chat.enableSend();
            return;
        }

        // Assign queryId — use server-provided query_id for feedback, or local counter for map
        let queryId = data.query_id || null;
        if (!queryId && data.action === 'query' && data.data) {
            queryId = ++queryIdCounter;
        }

        // Always render chat message
        const displayText = data.message || '(no message)';
        chat.addAssistantMessage(displayText, data, queryId);

        // Route to map based on action type
        if (mapReady) {
            dispatchToMap(data, queryId);
        }

        chat.enableSend();
        return;
    }

    // Unknown message type — log and re-enable input
    chat.addLog('warn', `Unknown message type: ${msg.type || '(none)'}`);
    chat.enableSend();
}

// ── Action-to-map dispatch ───────────────────────
async function dispatchToMap(data, queryId) {
    const action = data.action;

    try {
        // Skip if backend returned an error in data payload
        if (data.data?.error) {
            chat.addLog('warn', `Map rendering skipped: ${data.data.error}`);
            return;
        }

        if (action === 'query' && data.data) {
            // Pass raw data to map — normalization happens inside addQueryLayer
            await map.addQueryLayer(data.data, data.message || '', queryId);
        } else if (action === 'locate') {
            // Extract location from whichever response shape we received:
            //   /execute endpoint → data.data.source.location (uniform shape)
            //   /locate endpoint  → data.data.location (pre-extracted)
            //   /execute (legacy) → data.data.candidates[0].location (raw MCP result)
            const loc = data.data?.source?.location
                || data.data?.location
                || data.data?.candidates?.[0]?.location;
            const addr = data.data?.source?.address
                || data.data?.address
                || data.data?.candidates?.[0]?.address
                || data.message;
            if (loc?.x != null && loc?.y != null) {
                await map.addLocatePin(loc.x, loc.y, addr);
            }
        } else if (action === 'analyze' && data.data) {
            // Render all layers (incl. _buffer_zone) via the query layer pipeline
            await map.addQueryLayer(data.data, data.message || '', queryId);
        }
        // message, summarize, summarize_stat, search, unknown — no map action
    } catch (err) {
        console.warn('Map dispatch error:', err);
        chat.addLog('warn', `Map rendering skipped: ${err.message}`);
    }
}

// ── Global zoom helpers (used by chat buttons) ───
window.__zoomToLocate = (x, y) => {
    if (map.zoomToLocate) map.zoomToLocate();
};
window.__zoomToQuery = (queryId) => {
    if (map.zoomToQuery) map.zoomToQuery(queryId);
};

// ── Panel min/max button wiring ──────────────────
function wireMinMaxButtons() {
    const mainArea = document.querySelector('.main-area');
    const chatToggle = document.getElementById('chatPanelToggle');
    const mapToggle = document.getElementById('mapPanelToggle');

    if (!mainArea) return;

    if (chatToggle) {
        chatToggle.onclick = () => {
            if (mainArea.classList.contains('layout-chat-max')) {
                mainArea.classList.remove('layout-chat-max');
                chatToggle.textContent = '⊞';
            } else {
                mainArea.classList.remove('layout-map-max');
                mainArea.classList.add('layout-chat-max');
                chatToggle.textContent = '⊟';
                if (mapToggle) mapToggle.textContent = '⊞';
            }
        };
    }

    if (mapToggle) {
        mapToggle.onclick = () => {
            if (mainArea.classList.contains('layout-map-max')) {
                mainArea.classList.remove('layout-map-max');
                mapToggle.textContent = '⊞';
            } else {
                mainArea.classList.remove('layout-chat-max');
                mainArea.classList.add('layout-map-max');
                mapToggle.textContent = '⊟';
                if (chatToggle) chatToggle.textContent = '⊞';
            }
        };
    }
}
