"""
Tests for location picker feature.

The location picker is now a React component (LocationPicker.tsx) tested
via Vitest unit tests in src/features/map/map-components.test.tsx.
This file retains only server-level smoke tests.
"""

from fastapi.testclient import TestClient


class TestLocationPickerSmoke:
    """Verify the app serves correctly with location picker feature."""

    def test_app_serves_html(self):
        from web_app import app

        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
