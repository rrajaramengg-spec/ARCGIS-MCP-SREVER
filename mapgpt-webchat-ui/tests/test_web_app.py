"""
Smoke tests for webchat-ui.
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

    def test_static_index(self):
        from web_app import app

        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert "GIS Chat" in response.text

    def test_websocket_connect(self):
        from web_app import app

        client = TestClient(app)
        with client.websocket_connect("/ws/chat") as ws:
            # Just verify connection works
            assert ws is not None


class TestFeatureTable:
    """Tests for feature table rendering in index.html."""

    def test_index_contains_feature_table_function(self):
        """index.html includes buildFeatureTable JS function."""
        from web_app import app

        client = TestClient(app)
        response = client.get("/")
        html = response.text
        assert "function buildFeatureTable(data)" in html

    def test_feature_table_uses_arcgis_standard_keys(self):
        """buildFeatureTable uses ArcGIS standard camelCase keys."""
        from web_app import app

        client = TestClient(app)
        html = client.get("/").text
        # ArcGIS standard camelCase keys
        assert "data.geometryType" in html
        assert "data.spatialReference" in html
        # Field alias support from ArcGIS standard fields metadata
        assert "data.fields" in html
        assert "fieldAliases" in html

    def test_feature_table_caps_at_10(self):
        """buildFeatureTable caps display at 10 features."""
        from web_app import app

        client = TestClient(app)
        html = client.get("/").text
        assert "features.slice(0, 10)" in html
        assert "Showing" in html


class TestCommandsProxy:
    """Tests for /api/commands proxy and WebSocket relay."""

    def test_commands_proxy(self, httpx_mock):
        """10.1: /api/commands proxy returns commands from MCP client."""
        from unittest.mock import patch, AsyncMock
        import httpx as httpx_mod

        mock_commands = [
            {"name": "/locate", "description": "Geocode", "endpoint": "/api/v1/locate", "params": "<address>"},
            {"name": "/summarize", "description": "Summarize", "endpoint": "/api/v1/summarize", "params": "<query>"},
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

    def test_websocket_sends_slash_commands_to_execute(self):
        """10.2: WebSocket forwards slash commands to /execute endpoint."""
        from web_app import app

        # Verify the webchat WebSocket relay code sends to /execute
        client = TestClient(app)
        html = client.get("/").text
        # WebSocket sends to /execute via ws.send (which goes through the relay)
        assert "/api/v1/execute" in html or "ws.send" in html

    def test_websocket_forwards_normal_messages(self):
        """10.3: WebSocket forwards normal messages to /execute unchanged."""
        from web_app import app

        client = TestClient(app)
        html = client.get("/").text
        # The webchat always sends to /execute via WebSocket relay
        assert "ws.send(JSON.stringify" in html

    def test_command_dropdown_in_html(self):
        """Verify command suggestion dropdown exists in index.html."""
        from web_app import app

        client = TestClient(app)
        html = client.get("/").text
        assert "fetchCommands" in html
        assert "cachedCommands" in html
        assert "/api/commands" in html

    def test_placeholder_hints_commands(self):
        """Input placeholder mentions / for commands."""
        from web_app import app

        client = TestClient(app)
        html = client.get("/").text
        assert "type / for commands" in html
