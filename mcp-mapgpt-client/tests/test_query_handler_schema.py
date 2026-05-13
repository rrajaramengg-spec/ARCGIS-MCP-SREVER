"""
Unit tests for QueryHandler layer name resolution and execution graph enrichment.

Phase 1 backend schema changes:
- _resolve_layer_name()
- _build_node_label()
- Enriched execution_graph (depends_on, label, edges)
- layer_name / layer_url in result entries
"""

import pytest
from unittest.mock import MagicMock

from core.llm_service import LLMService
from core.mcp_client import MCPClient
from core.orchestrator.query_handler import QueryHandler


def _make_handler(rag_layers=None):
    """Create a QueryHandler with mocked MCP and LLM."""
    mock_mcp = MagicMock(spec=MCPClient)
    mock_llm = MagicMock(spec=LLMService)
    handler = QueryHandler(
        mcp=mock_mcp,
        llm=mock_llm,
        prompts={"query_instructions": {"system": "test", "human": "{context}\n{query}"}},
        tools_cache=[],
    )
    if rag_layers is not None:
        handler._last_rag_layers = rag_layers
    return handler


# ── _resolve_layer_name ───────────────────────────


class TestResolveLayerName:
    """Tests for _resolve_layer_name()."""

    def test_match_found(self):
        handler = _make_handler(rag_layers=[
            {"url": "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0", "layer_name": "PSAP"},
            {"url": "https://services.arcgis.com/abc/rest/services/Fire/MapServer/0", "layer_name": "Fire Stations"},
        ])
        result = handler._resolve_layer_name(
            "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0"
        )
        assert result == "PSAP"

    def test_no_match(self):
        handler = _make_handler(rag_layers=[
            {"url": "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0", "layer_name": "PSAP"},
        ])
        result = handler._resolve_layer_name(
            "https://services.arcgis.com/abc/rest/services/Unknown/MapServer/0"
        )
        assert result is None

    def test_empty_rag_layers(self):
        handler = _make_handler(rag_layers=[])
        result = handler._resolve_layer_name(
            "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0"
        )
        assert result is None

    def test_empty_layer_url(self):
        handler = _make_handler(rag_layers=[
            {"url": "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0", "layer_name": "PSAP"},
        ])
        result = handler._resolve_layer_name("")
        assert result is None

    def test_none_rag_layers(self):
        handler = _make_handler()
        handler._last_rag_layers = []
        result = handler._resolve_layer_name("https://example.com")
        assert result is None

    def test_rag_layer_missing_layer_name_key(self):
        handler = _make_handler(rag_layers=[
            {"url": "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0"},
        ])
        result = handler._resolve_layer_name(
            "https://services.arcgis.com/abc/rest/services/PSAP_911/MapServer/0"
        )
        assert result is None


# ── _build_node_label ─────────────────────────────


class TestBuildNodeLabel:
    """Tests for _build_node_label()."""

    def _make_node(self, **kwargs):
        """Create a mock node with given attributes."""
        node = MagicMock()
        for k, v in kwargs.items():
            setattr(node, k, v)
        return node

    def test_geocode_label(self):
        handler = _make_handler()
        node = self._make_node(node_type="geocode", address="123 Main St")
        assert handler._build_node_label(node) == "Geocode '123 Main St'"

    def test_geocode_empty_address(self):
        handler = _make_handler()
        node = self._make_node(node_type="geocode", address="")
        assert handler._build_node_label(node) == "Geocode"

    def test_query_with_rag_match(self):
        handler = _make_handler(rag_layers=[
            {"url": "https://example.com/PSAP/MapServer/0", "layer_name": "PSAP"},
        ])
        node = self._make_node(
            node_type="query",
            layer_url="https://example.com/PSAP/MapServer/0",
        )
        assert handler._build_node_label(node) == "Query PSAP"

    def test_query_url_fallback(self):
        handler = _make_handler(rag_layers=[])
        node = self._make_node(
            node_type="query",
            layer_url="https://example.com/rest/services/PSAP_911/MapServer/0",
        )
        # Falls back to last non-numeric URL segment
        assert handler._build_node_label(node) == "Query MapServer"

    def test_query_no_url(self):
        handler = _make_handler(rag_layers=[])
        node = self._make_node(node_type="query", layer_url="")
        assert handler._build_node_label(node) == "Query"

    def test_buffer_label(self):
        handler = _make_handler()
        node = self._make_node(
            node_type="buffer", distance=5, unit="miles",
            layer_url="",
        )
        assert handler._build_node_label(node) == "Buffer 5miles"

    def test_proximity_label(self):
        handler = _make_handler(rag_layers=[
            {"url": "https://example.com/Fire/MapServer/0", "layer_name": "Fire Stations"},
        ])
        node = self._make_node(
            node_type="proximity",
            layer_url="https://example.com/Fire/MapServer/0",
        )
        assert handler._build_node_label(node) == "Find Nearby Fire Stations"

    def test_union_label(self):
        handler = _make_handler()
        node = self._make_node(node_type="union", layer_url="")
        assert handler._build_node_label(node) == "Union"

    def test_spatial_join_label(self):
        handler = _make_handler(rag_layers=[])
        node = self._make_node(
            node_type="spatial_join",
            layer_url="https://example.com/rest/services/Parcels/MapServer/0",
        )
        assert handler._build_node_label(node) == "Spatial Join MapServer"

    def test_summarize_label(self):
        handler = _make_handler()
        node = self._make_node(node_type="summarize", layer_url="")
        assert handler._build_node_label(node) == "Summarize"

    def test_count_label(self):
        handler = _make_handler(rag_layers=[
            {"url": "https://example.com/PSAP/MapServer/0", "layer_name": "PSAP"},
        ])
        node = self._make_node(
            node_type="count",
            layer_url="https://example.com/PSAP/MapServer/0",
        )
        assert handler._build_node_label(node) == "Count PSAP"

    def test_unknown_node_type_returns_id(self):
        handler = _make_handler()
        node = self._make_node(node_type="unknown", node_id="n99", layer_url="")
        assert handler._build_node_label(node) == "n99"
