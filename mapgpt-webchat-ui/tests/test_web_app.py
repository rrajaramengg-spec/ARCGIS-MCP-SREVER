"""
Smoke tests for mapgpt-webchat-ui.

After the React migration, the SPA is served from dist/ (Vite build)
or falls back to static/ (legacy). These tests verify the FastAPI server,
proxy routes, and WebSocket relay — NOT the React component behavior
(covered by Vitest unit tests).
"""

from fastapi.testclient import TestClient


class TestWebApp:
    """Smoke tests for the web app."""

    def test_health(self):
        from web_app import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_root_serves_html(self):
        from web_app import app

        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        # Should serve HTML (either React SPA or legacy index.html)
        assert "text/html" in response.headers.get("content-type", "")

    def test_websocket_connect(self):
        from web_app import app

        client = TestClient(app)
        with client.websocket_connect("/ws/chat") as ws:
            # Just verify connection works
            assert ws is not None


class TestCommandsProxy:
    """Tests for /api/commands proxy and WebSocket relay."""

    def test_commands_proxy(self, httpx_mock):
        """10.1: /api/commands proxy returns commands from mcp-mapgpt-client."""
        from unittest.mock import patch, AsyncMock

        mock_commands = [
            {"name": "/locate", "description": "Geocode", "endpoint": "/api/mapgpt/v1/locate", "params": "<address>"},
            {"name": "/summarize", "description": "Summarize", "endpoint": "/api/mapgpt/v1/summarize", "params": "<query>"},
        ]

        from web_app import app

        # Mock httpx.AsyncClient to return our commands
        with patch("web_app.httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_commands
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            client = TestClient(app)
            response = client.get("/api/commands")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_placeholder_hints_commands(self):
        """Input placeholder mentions / for commands."""
        from web_app import app

        client = TestClient(app)
        html = client.get("/").text
        assert "type / for commands" in html


class TestFeedbackProxy:
    """Tests for /api/user-feedback proxy route."""

    def test_feedback_proxy_success(self):
        """Feedback POST is forwarded to mcp-mapgpt-client and response returned."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from web_app import app

        upstream_response = {"status": "ok", "action": "promoted"}

        with patch("web_app.httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = upstream_response
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            client = TestClient(app)
            response = client.post("/api/user-feedback", json={
                "session_id": "test-session",
                "query_id": "test-query-id",
                "feedback": "up",
            })
            assert response.status_code == 200
            assert response.json() == upstream_response

    def test_feedback_proxy_upstream_error(self):
        """Returns 502 when upstream returns non-2xx status."""
        from unittest.mock import patch, AsyncMock
        from web_app import app

        with patch("web_app.httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 422
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            client = TestClient(app)
            response = client.post("/api/user-feedback", json={
                "session_id": "s", "query_id": "q", "feedback": "up",
            })
            assert response.status_code == 502
            assert "Upstream returned HTTP 422" in response.json()["error"]

    def test_feedback_proxy_connection_error(self):
        """Returns 502 when upstream is unreachable."""
        from unittest.mock import patch, AsyncMock
        import httpx as httpx_mod
        from web_app import app

        with patch("web_app.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(
                side_effect=httpx_mod.ConnectError("Connection refused")
            )
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            client = TestClient(app)
            response = client.post("/api/user-feedback", json={
                "session_id": "s", "query_id": "q", "feedback": "down",
            })
            assert response.status_code == 502
            assert "error" in response.json()
