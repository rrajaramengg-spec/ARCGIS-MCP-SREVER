"""
Integration tests for mcp-mapgpt-client REST API endpoints.
Uses FastAPI TestClient.
"""

from unittest.mock import MagicMock, patch


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_degraded_when_mcp_disconnected(self):
        """Health returns 503 when MCP client is not connected."""
        # Patch before importing app
        with patch("main.mcp_client") as mock_mcp:
            mock_mcp.is_connected = False
            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")
            assert response.status_code == 503
            assert response.json()["status"] == "degraded"


class TestExecuteEndpoint:
    """Tests for /api/mapgpt/v1/execute endpoint."""

    def test_execute_missing_query_returns_422(self):
        """Missing query field returns validation error."""
        from fastapi.testclient import TestClient
        from main import app
        from core.providers import get_orchestrator

        mock_orch = MagicMock()
        app.dependency_overrides[get_orchestrator] = lambda: mock_orch
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/mapgpt/v1/execute", json={})
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_orchestrator, None)

    def test_old_prefix_returns_404(self):
        """Old /api/v1/ prefix should not be registered."""
        with patch("main.mcp_client") as mock_mcp:
            mock_mcp.is_connected = True
            from fastapi.testclient import TestClient
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/v1/execute", json={"query": "test"})
            assert response.status_code == 404


class TestIngestEndpoint:
    """Tests for /api/mapgpt/v1/ingest endpoint."""

    def test_ingest_missing_fields_returns_422(self):
        """Missing required fields returns validation error."""
        from fastapi.testclient import TestClient
        from main import app
        from core.providers import get_rag_service

        mock_rag = MagicMock()
        app.dependency_overrides[get_rag_service] = lambda: mock_rag
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/mapgpt/v1/ingest", json={"content": "test"})
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_rag_service, None)
