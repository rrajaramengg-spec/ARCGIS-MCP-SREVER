# webchat-ui — Browser Debugging Guide

## Prerequisites

- Docker Compose running with `--profile demo`
- Browser with DevTools (Chrome/Edge recommended)

## 1. Open the UI

Navigate to `http://localhost:8080`. You should see a split layout: chat on the left, map on the right.

## 2. Check Console for Errors

Open DevTools -> Console tab. On a healthy load you should see:

- No errors from `app.js`, `chat.js`, `api.js`, `map.js`
- ArcGIS SDK modules loading from `js.arcgis.com`
- WebSocket connection message in the Logs panel

## 3. Verify Static Files

In DevTools -> Network tab, confirm these return 200:

| URL | File |
|-----|------|
| `/css/styles.css` | Extracted CSS |
| `/js/app.js` | Entry point module |
| `/js/config.js` | Configuration constants |
| `/js/api.js` | WebSocket/HTTP client |
| `/js/chat.js` | Chat UI module |
| `/js/map.js` | ArcGIS map module |

## 4. Debug WebSocket Messages

Open the Logs panel (click "Logs" at the bottom of the chat panel). It shows:

- **info** (blue) — connection status, response keys
- **sent** (green) — outgoing queries
- **recv** (orange) — incoming responses (truncated to 200 chars)
- **warn** (yellow) — disconnections, map rendering skips
- **error** (red) — connection errors, fetch failures

## 5. Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Map unavailable" | CDN unreachable | Check network/firewall for `js.arcgis.com` |
| Features render but no popups | Missing field metadata | Check if response has `fields` array |
| Slow first load | ArcGIS SDK (~2-3MB) | Normal for first load; cached after |
| WebSocket disconnects | Backend not running | Ensure the MCP client is up on port 8002 |
