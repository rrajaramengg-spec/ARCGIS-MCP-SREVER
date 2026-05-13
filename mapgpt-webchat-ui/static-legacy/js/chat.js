// ── Chat UI Module ───────────────────────────────
import * as api from './api.js';
import { normalizeQueryResponse } from './normalize.js';

// ── DOM refs ─────────────────────────────────────
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const statusText = document.getElementById('status-text');
const statusDot = document.getElementById('status-dot');
const dropdownEl = document.getElementById('dropdown');
const logsPanel = document.getElementById('logsPanel');
const logsBody = document.getElementById('logsBody');
const logCountBadge = document.getElementById('logCount');
const logsToggleBar = document.getElementById('logsToggleBar');
const logsToggleLabel = document.getElementById('logsToggleLabel');
const clearLogsBtn = document.getElementById('clearLogs');

let logCount = 0;
let logsOpen = false;

// ── Raw response data store (capped) ────────────
const rawDataStore = new Map();
const MAX_RAW_ENTRIES = 50;

// ── Logging ──────────────────────────────────────
export function addLog(level, text) {
    logCount++;
    logCountBadge.textContent = logCount;
    const el = document.createElement('div');
    el.className = `log-entry ${level}`;
    const now = new Date().toLocaleTimeString();
    el.innerHTML = `<span class="log-time">${now}</span>${escapeHtml(text)}`;
    logsBody.appendChild(el);
    logsBody.scrollTop = logsBody.scrollHeight;
}

// ── Status ───────────────────────────────────────
export function updateStatus(state) {
    if (state === 'connected') {
        statusText.textContent = 'Connected';
        statusDot.classList.add('connected');
        sendBtn.disabled = false;
    } else if (state === 'disconnected') {
        statusText.textContent = 'Disconnected — reconnecting...';
        statusDot.classList.remove('connected');
        sendBtn.disabled = true;
        hideThinking();
    } else if (state === 'error') {
        statusText.textContent = 'Connection error';
    }
}

// ── Thinking indicator ───────────────────────────
export function showThinking() {
    const el = document.createElement('div');
    el.className = 'thinking';
    el.id = 'thinking';
    el.innerHTML = '<span></span><span></span><span></span>';
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

export function hideThinking() {
    const el = document.getElementById('thinking');
    if (el) el.remove();
    const prog = document.getElementById('progress-text');
    if (prog) prog.remove();
}

export function showProgress(stepText) {
    let el = document.getElementById('progress-text');
    if (!el) {
        el = document.createElement('div');
        el.id = 'progress-text';
        el.className = 'progress-step';
        const thinking = document.getElementById('thinking');
        if (thinking) {
            thinking.after(el);
        } else {
            messagesEl.appendChild(el);
        }
    }
    el.textContent = stepText;
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Message rendering ────────────────────────────
export function addUserMessage(text) {
    const el = document.createElement('div');
    el.className = 'message user';
    el.textContent = text;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

export function addAssistantMessage(text, rawData, queryId) {
    const el = document.createElement('div');
    el.className = 'message assistant';

    const html = marked.parse(text);
    let content = html;

    // Feature summary + table for query actions only
    if (rawData?.action === 'query' && (rawData?.results || rawData?.data)) {
        const normalized = normalizeQueryResponse(rawData) || normalizeQueryResponse(rawData.data);

        // Feature count summary — below markdown, above table
        if (normalized) {
            content += buildFeatureSummary(normalized);
        }

        // Feature table — only when there are actual features
        if (normalized && normalized.layers.length > 0) {
            const tableLayer = normalized.layers.find(l => l.role === 'child') || normalized.layers[0];
            if (tableLayer.features && tableLayer.features.length > 0) {
                content += buildFeatureTable(tableLayer);
            }
        }

        // Show on Map button — only when there are renderable features
        if (normalized && normalized.layers.some(l => l.features && l.features.length > 0)) {
            content += `<button class="map-action-btn" onclick="window.__zoomToQuery('${queryId}')">🗺️ Show on Map</button>`;
        }
    }

    // Feature summary + tables for analyze actions
    if (rawData?.action === 'analyze' && (rawData?.results || rawData?.data)) {
        if (rawData.data?.source?.error) {
            content += `<div class="message error">${escapeHtml(rawData.data.source.error)}</div>`;
        } else {
            const normalized = normalizeQueryResponse(rawData) || normalizeQueryResponse(rawData.data);
            if (normalized) {
                content += buildFeatureSummary(normalized);
                // Render each result layer as a separate table
                for (const layer of normalized.layers) {
                    if (layer.role === 'parent') continue;
                    if (layer.bufferZone) continue;
                    if (layer.features && layer.features.length > 0) {
                        content += buildFeatureTable(layer);
                    }
                }
                if (normalized.layers.some(l => l.features && l.features.length > 0)) {
                    content += `<button class="map-action-btn" onclick="window.__zoomToQuery('${queryId}')">🗺️ Show on Map</button>`;
                }
            }
        }
    }

    // Locate zoom button — only for valid locations
    if (rawData?.action === 'locate') {
        // Try new results[] format first (geocode entry), then legacy data paths
        let loc = null;
        if (Array.isArray(rawData?.results)) {
            const geo = rawData.results.find(r => r.type === 'geocode');
            if (geo?.location) loc = geo.location;
        }
        if (!loc) {
            loc = rawData?.data?.source?.location
                || rawData?.data?.location
                || rawData?.data?.candidates?.[0]?.location;
        }
        if (loc?.x != null && loc?.y != null) {
            content += `<button class="map-action-btn" onclick="window.__zoomToLocate(${loc.x}, ${loc.y})">📍 Zoom</button>`;
        }
        // Render children results if present
        if (rawData?.results?.length > 0 || rawData?.data?.results?.length > 0) {
            const normalized = normalizeQueryResponse(rawData) || normalizeQueryResponse(rawData.data);
            if (normalized) {
                content += buildFeatureSummary(normalized);
                for (const layer of normalized.layers) {
                    if (layer.role === 'parent') continue;
                    if (layer.features && layer.features.length > 0) {
                        content += buildFeatureTable(layer);
                    }
                }
                if (normalized.layers.some(l => l.features && l.features.length > 0)) {
                    content += `<button class="map-action-btn" onclick="window.__zoomToQuery('${queryId}')">🗺️ Show on Map</button>`;
                }
            }
        }
    }

    // Raw response modal trigger — only for data-bearing action types
    if (rawData && (rawData.data || rawData.results) && ['query', 'search', 'analyze', 'locate'].includes(rawData.action)) {
        const rawId = 'raw-' + Date.now();
        rawDataStore.set(rawId, rawData);
        if (rawDataStore.size > MAX_RAW_ENTRIES) {
            rawDataStore.delete(rawDataStore.keys().next().value);
        }
        content += `<div class="raw-toggle" onclick="window.__showRawModal('${rawId}')">&#9654; View raw response</div>`;
    }
    el.innerHTML = content;
    el.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));

    // ── Feedback buttons (non-error responses with queryId) ──
    if (queryId && rawData && rawData.action !== 'error') {
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'feedback-container';

        const upBtn = document.createElement('button');
        upBtn.className = 'feedback-btn';
        upBtn.textContent = '👍';
        upBtn.title = 'Helpful response';

        const downBtn = document.createElement('button');
        downBtn.className = 'feedback-btn';
        downBtn.textContent = '👎';
        downBtn.title = 'Not helpful';

        const handleFeedback = async (feedback, activeBtn, otherBtn) => {
            upBtn.disabled = true;
            downBtn.disabled = true;
            activeBtn.classList.add('active');
            try {
                const resp = await fetch('/api/user-feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: api.getSessionId(),
                        query_id: String(queryId),
                        feedback,
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            } catch (err) {
                // Revert on failure
                upBtn.disabled = false;
                downBtn.disabled = false;
                activeBtn.classList.remove('active');
                console.error('Feedback failed:', err);
            }
        };

        upBtn.onclick = () => handleFeedback('up', upBtn, downBtn);
        downBtn.onclick = () => handleFeedback('down', downBtn, upBtn);

        feedbackDiv.appendChild(upBtn);
        feedbackDiv.appendChild(downBtn);
        el.appendChild(feedbackDiv);
    }

    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

export function addErrorMessage(text) {
    const el = document.createElement('div');
    el.className = 'message error';
    el.textContent = text;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}


// ── Raw Response Modal ───────────────────────────
const rawModal = document.getElementById('rawModal');
const rawModalBody = document.getElementById('rawModalBody');
const rawModalTitle = document.getElementById('rawModalTitle');
const rawModalClose = document.getElementById('rawModalClose');
const rawModalCopy = document.getElementById('rawModalCopy');
let _currentRawJson = '';

function closeRawModal() {
    if (rawModal) rawModal.classList.remove('visible');
    _currentRawJson = '';
}

if (rawModal) {
    rawModalClose.onclick = closeRawModal;
    rawModal.onclick = (e) => { if (e.target === rawModal) closeRawModal(); };
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && rawModal.classList.contains('visible')) closeRawModal();
    });
    rawModalCopy.onclick = () => {
        navigator.clipboard.writeText(_currentRawJson).then(() => {
            rawModalCopy.classList.add('copied');
            rawModalCopy.innerHTML = '&#10003; Copied';
            setTimeout(() => {
                rawModalCopy.classList.remove('copied');
                rawModalCopy.innerHTML = '&#128203; Copy';
            }, 1500);
        });
    };
}

window.__showRawModal = function (id) {
    const data = rawDataStore.get(id);
    if (!data || !rawModal) return;
    _currentRawJson = JSON.stringify(data, null, 2);
    const action = data.action || 'response';
    const layer = data.data?.layer || data.tool_name || '';
    rawModalTitle.textContent = `Raw Response — ${action}${layer ? ' · ' + layer : ''}`;
    rawModalBody.innerHTML = `<pre>${escapeHtml(_currentRawJson)}</pre>`;
    rawModal.classList.add('visible');
};

// ── HTML escaping ────────────────────────────────
function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Feature summary builder ──────────────────────
const MAX_FEATURES = 500;

export function buildFeatureSummary(normalized) {
    if (!normalized || !Array.isArray(normalized.layers) || normalized.layers.length === 0) return '';

    const layers = normalized.layers;

    // Check if all layers have zero features
    const allZero = layers.every(l => (l.count || 0) === 0 && (!l.features || l.features.length === 0));
    if (allZero) {
        return '<div class="feature-summary-empty">No features found</div>';
    }

    const badges = [];
    for (const layer of layers) {
        const name = escapeHtml(layer.name || layer.role || 'Query');
        const count = layer.count != null ? layer.count : (layer.features ? layer.features.length : 0);

        // Buffer zone — show radius info instead of feature count
        if (layer.bufferZone && layer.features && layer.features.length > 0) {
            const attrs = layer.features[0]?.attributes || {};
            const radius = attrs.radius || '';
            const unit = attrs.unit || '';
            badges.push(`<span class="feature-badge feature-badge-parent">Buffer: ${radius} ${escapeHtml(unit)}</span>`);
            continue;
        }

        let text = `${name}: ${count.toLocaleString()}`;

        // Render-cap indicator
        if (count > MAX_FEATURES && layer.features && layer.features.length > 0) {
            text += ` (showing ${MAX_FEATURES} on map)`;
        }

        // Count-only indicator
        if (layer.countOnly) {
            text += ' (count only)';
        }

        const role = layer.role || 'primary';
        badges.push(`<span class="feature-badge feature-badge-${escapeHtml(role)}">${text}</span>`);
    }

    return `<div class="feature-summary">${badges.join('<span class="feature-badge-separator"> · </span>')}</div>`;
}

// ── Feature table builder ────────────────────────
export function buildFeatureTable(layerGroup) {
    if (!layerGroup || !Array.isArray(layerGroup.features) || layerGroup.features.length === 0) return '';

    const features = layerGroup.features;
    const totalCount = layerGroup.count || features.length;
    const displayFeatures = features.slice(0, 10);

    const firstAttrs = displayFeatures[0]?.attributes;
    if (!firstAttrs) return '';
    const columns = Object.keys(firstAttrs).filter(
        k => !['SHAPE', 'SHAPE_Length', 'SHAPE_Area'].includes(k)
    );
    if (columns.length === 0) return '';

    // Build field alias map
    const fieldAliases = {};
    if (Array.isArray(layerGroup.fields)) {
        layerGroup.fields.forEach(f => {
            if (f.name && f.alias) fieldAliases[f.name] = f.alias;
        });
    }

    // Metadata header
    const metaParts = [];
    if (layerGroup.name) metaParts.push(layerGroup.name);
    if (layerGroup.geometryType) metaParts.push(layerGroup.geometryType);
    if (layerGroup.spatialReference?.wkid) metaParts.push('WKID: ' + layerGroup.spatialReference.wkid);
    metaParts.push(totalCount + ' feature' + (totalCount !== 1 ? 's' : ''));
    const metaHtml = `<div class="feature-table-header">${escapeHtml(metaParts.join(' · '))}</div>`;

    // Table
    let tableHtml = '<table><thead><tr>';
    columns.forEach(col => {
        const header = fieldAliases[col] || col;
        tableHtml += `<th>${escapeHtml(header)}</th>`;
    });
    tableHtml += '</tr></thead><tbody>';
    displayFeatures.forEach(f => {
        tableHtml += '<tr>';
        columns.forEach(col => {
            const val = f.attributes?.[col];
            tableHtml += `<td>${val != null ? escapeHtml(String(val)) : ''}</td>`;
        });
        tableHtml += '</tr>';
    });
    tableHtml += '</tbody></table>';

    let footerHtml = '';
    if (totalCount > 10) {
        footerHtml = `<div class="feature-table-footer">Showing ${displayFeatures.length} of ${totalCount}</div>`;
    }

    return `<div class="feature-table-container">${metaHtml}${tableHtml}${footerHtml}</div>`;
}

// ── Dropdown (commands / resources) ──────────────
function hideDropdown() {
    dropdownEl.classList.remove('visible');
    dropdownEl.innerHTML = '';
}

function showDropdown(items, onSelect) {
    dropdownEl.innerHTML = '';
    items.forEach(item => {
        const el = document.createElement('div');
        el.className = 'dropdown-item';
        el.textContent = item.label || item.name || item.uri || String(item);
        el.onclick = () => { onSelect(item); hideDropdown(); };
        dropdownEl.appendChild(el);
    });
    dropdownEl.classList.add('visible');
}

// ── Input wiring ─────────────────────────────────
export function getInputText() {
    return inputEl.value.trim();
}

export function clearInput() {
    inputEl.value = '';
}

export function appendInputText(text) {
    const current = inputEl.value;
    inputEl.value = current ? current.trimEnd() + ' ' + text : text;
    inputEl.focus();
}

export function disableSend() {
    sendBtn.disabled = true;
}

export function enableSend() {
    sendBtn.disabled = false;
}

// ── Initialize chat event handlers ───────────────
export function init(onSend) {
    // Logs toggle
    logsToggleBar.onclick = () => {
        logsOpen = !logsOpen;
        logsPanel.classList.toggle('open', logsOpen);
        logsToggleLabel.innerHTML = logsOpen ? '&#9660; Logs' : '&#9650; Logs';
    };

    clearLogsBtn.onclick = () => {
        logsBody.innerHTML = '';
        logCount = 0;
        logCountBadge.textContent = '0';
    };

    // Input handlers
    inputEl.addEventListener('input', async () => {
        const val = inputEl.value;
        if (val.startsWith('/')) {
            const cmds = await api.fetchCommands();
            const typed = val.toLowerCase();
            const filtered = cmds.filter(c =>
                c.name.toLowerCase().startsWith(typed) || typed === '/'
            );
            if (filtered.length > 0) {
                showDropdown(
                    filtered.map(c => ({
                        label: `${c.name} — ${c.description}`,
                        name: c.name,
                    })),
                    (item) => {
                        inputEl.value = item.name + ' ';
                        inputEl.focus();
                    }
                );
            } else {
                hideDropdown();
            }
        } else if (val === '@') {
            const resources = await api.fetchResources();
            if (resources.length > 0) {
                showDropdown(resources, (r) => {
                    inputEl.value += (r.uri || r.name || '');
                    inputEl.focus();
                });
            }
        } else {
            hideDropdown();
        }
    });

    sendBtn.onclick = () => onSend();
    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') onSend();
        if (e.key === 'Escape') hideDropdown();
    });
}
