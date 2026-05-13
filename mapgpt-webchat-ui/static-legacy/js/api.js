// ── WebSocket & HTTP API Client ───────────────────
import { API_COMMANDS, API_RESOURCES, WS_PATH } from './config.js';

let ws = null;
let messageHandler = null;
let statusHandler = null;
let logHandler = null;
let cachedCommands = null;
let sessionId = null;

function log(level, text) {
    if (logHandler) logHandler(level, text);
}

// ── WebSocket ────────────────────────────────────
export function connect() {
    sessionId = crypto.randomUUID();
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}${WS_PATH}`);
    log('info', 'Connecting to WebSocket...');

    ws.onopen = () => {
        if (statusHandler) statusHandler('connected');
        log('info', 'WebSocket connected');
    };

    ws.onmessage = (event) => {
        let msg;
        try {
            msg = JSON.parse(event.data);
        } catch (err) {
            log('error', `Malformed JSON from server: ${err.message}`);
            if (messageHandler) messageHandler({ type: 'error', data: { error: 'Received malformed response from server' } });
            return;
        }
        log('recv', `Response: ${JSON.stringify(msg).substring(0, 200)}...`);
        if (messageHandler) messageHandler(msg);
    };

    ws.onclose = () => {
        if (statusHandler) statusHandler('disconnected');
        log('warn', 'WebSocket disconnected, reconnecting in 3s...');
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        if (statusHandler) statusHandler('error');
        log('error', 'WebSocket error');
    };
}

export function send(text) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ message: text, session_id: sessionId }));
        log('sent', `Query: ${text}`);
        return true;
    }
    return false;
}

export function isConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
}

export function getSessionId() {
    return sessionId;
}

export function onMessage(handler) {
    messageHandler = handler;
}

export function onStatus(handler) {
    statusHandler = handler;
}

export function onLog(handler) {
    logHandler = handler;
}

// ── HTTP fetch wrappers ──────────────────────────
export async function fetchCommands() {
    if (cachedCommands) return cachedCommands;
    try {
        const resp = await fetch(API_COMMANDS);
        const cmds = await resp.json();
        if (Array.isArray(cmds)) {
            cachedCommands = cmds;
            return cmds;
        }
    } catch (err) {
        log('error', 'Failed to fetch commands: ' + err);
    }
    return [];
}

export async function fetchResources() {
    try {
        const resp = await fetch(API_RESOURCES);
        const resources = await resp.json();
        if (Array.isArray(resources)) return resources;
    } catch (err) {
        log('error', 'Failed to fetch resources: ' + err);
    }
    return [];
}
