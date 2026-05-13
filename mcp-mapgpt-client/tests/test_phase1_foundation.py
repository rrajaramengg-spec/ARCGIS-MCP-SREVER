"""Unit tests for Phase 1 — tool_names, results, and refactored ConversationHistory."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock redis before importing core.history to avoid ModuleNotFoundError
if "redis" not in sys.modules:
    sys.modules["redis"] = MagicMock()
    sys.modules["redis.asyncio"] = MagicMock()

from core.history import ConversationHistory

# ---------------------------------------------------------------------------
# tool_names.py
# ---------------------------------------------------------------------------


class TestToolNames:
    """Verify tool_names constants and ARCGIS_TOOL_NAMES frozenset."""

    def test_all_14_tool_constants_exist(self):
        from core.tool_names import (
            ARCGIS_TOOL_NAMES,
            BUFFER_AND_QUERY,
            COUNT_FEATURES,
            EXECUTE_QUERY_PLAN,
            FIND_NEARBY,
            GEOCODE,
            GET_FEATURE_TABLE,
            JOIN_LAYERS,
            QUERY_FEATURES,
            REVERSE_GEOCODE,
            SEARCH_CONTENT,
            SEARCH_LAYERS,
            SPATIAL_JOIN_QUERY,
            SUMMARIZE_FIELD,
            UNION_GEOMETRIES,
        )

        assert len(ARCGIS_TOOL_NAMES) == 14
        # Each constant is in the frozenset
        assert QUERY_FEATURES in ARCGIS_TOOL_NAMES
        assert COUNT_FEATURES in ARCGIS_TOOL_NAMES
        assert GEOCODE in ARCGIS_TOOL_NAMES
        assert REVERSE_GEOCODE in ARCGIS_TOOL_NAMES
        assert BUFFER_AND_QUERY in ARCGIS_TOOL_NAMES
        assert FIND_NEARBY in ARCGIS_TOOL_NAMES
        assert SUMMARIZE_FIELD in ARCGIS_TOOL_NAMES
        assert GET_FEATURE_TABLE in ARCGIS_TOOL_NAMES
        assert SPATIAL_JOIN_QUERY in ARCGIS_TOOL_NAMES
        assert JOIN_LAYERS in ARCGIS_TOOL_NAMES
        assert EXECUTE_QUERY_PLAN in ARCGIS_TOOL_NAMES
        assert SEARCH_CONTENT in ARCGIS_TOOL_NAMES
        assert SEARCH_LAYERS in ARCGIS_TOOL_NAMES
        assert UNION_GEOMETRIES in ARCGIS_TOOL_NAMES

    def test_frozenset_is_immutable(self):
        from core.tool_names import ARCGIS_TOOL_NAMES

        with pytest.raises(AttributeError):
            ARCGIS_TOOL_NAMES.add("new_tool")

    def test_tool_name_values_are_strings(self):
        from core.tool_names import ARCGIS_TOOL_NAMES

        for name in ARCGIS_TOOL_NAMES:
            assert isinstance(name, str)
            assert len(name) > 0

    def test_matches_server_expected_tools(self):
        """Constants match the authoritative server tool list."""
        from core.tool_names import ARCGIS_TOOL_NAMES

        server_tools = {
            "query_features", "count_features", "spatial_join_query",
            "join_layers", "execute_query_plan", "search_content",
            "search_layers", "summarize_field", "get_feature_table",
            "buffer_and_query", "find_nearby", "geocode",
            "reversegeocode", "union_geometries",
        }
        assert ARCGIS_TOOL_NAMES == server_tools


# ---------------------------------------------------------------------------
# results.py
# ---------------------------------------------------------------------------


class TestFeatureSetResult:
    """FeatureSetResult typed model tests."""

    def test_validates_arcgis_response(self):
        from core.orchestrator.graph.results import FeatureSetResult

        data = {
            "features": [{"attributes": {"NAME": "Springfield"}}],
            "count": 1,
            "geometryType": "esriGeometryPolygon",
            "spatialReference": {"wkid": 4326},
        }
        result = FeatureSetResult.model_validate(data)
        assert result.count == 1
        assert result.geometryType == "esriGeometryPolygon"
        assert len(result.features) == 1

    def test_extra_fields_preserved(self):
        from core.orchestrator.graph.results import FeatureSetResult

        data = {
            "features": [],
            "count": 0,
            "displayFieldName": "NAME",
            "someNewField": "value",
        }
        result = FeatureSetResult.model_validate(data)
        assert result.count == 0
        assert result.displayFieldName == "NAME"
        assert result.someNewField == "value"

    def test_defaults_on_empty_input(self):
        from core.orchestrator.graph.results import FeatureSetResult

        result = FeatureSetResult.model_validate({})
        assert result.features == []
        assert result.count == 0
        assert result.geometryType is None

    def test_error_response_defaults(self):
        """MCP error response gets defaults, not validation error."""
        from core.orchestrator.graph.results import FeatureSetResult

        result = FeatureSetResult.model_validate({"error": "Layer not found"})
        assert result.features == []
        assert result.count == 0


class TestGeocodeResult:
    def test_validates_geocode_response(self):
        from core.orchestrator.graph.results import GeocodeResult

        data = {
            "candidates": [{"address": "123 Main St", "location": {"x": -105.0, "y": 39.7}}],
        }
        result = GeocodeResult.model_validate(data)
        assert len(result.candidates) == 1
        assert result.candidates[0]["location"]["x"] == -105.0

    def test_empty_candidates(self):
        from core.orchestrator.graph.results import GeocodeResult

        result = GeocodeResult.model_validate({})
        assert result.candidates == []
        assert result.location is None


class TestCountResult:
    def test_validates_count(self):
        from core.orchestrator.graph.results import CountResult

        result = CountResult.model_validate({"count": 42})
        assert result.count == 42

    def test_default_zero(self):
        from core.orchestrator.graph.results import CountResult

        result = CountResult.model_validate({})
        assert result.count == 0


class TestBufferResult:
    def test_validates_buffer(self):
        from core.orchestrator.graph.results import BufferResult

        data = {"buffer_geometry": {"rings": [[[0, 0], [1, 0], [1, 1]]]}}
        result = BufferResult.model_validate(data)
        assert "rings" in result.buffer_geometry

    def test_default_empty(self):
        from core.orchestrator.graph.results import BufferResult

        result = BufferResult.model_validate({})
        assert result.buffer_geometry == {}


class TestSummaryResult:
    def test_validates_summary(self):
        from core.orchestrator.graph.results import SummaryResult

        data = {"statistics": {"min": 0, "max": 100}, "field_name": "POP"}
        result = SummaryResult.model_validate(data)
        assert result.field_name == "POP"
        assert result.statistics["max"] == 100

    def test_model_dump_roundtrip(self):
        from core.orchestrator.graph.results import SummaryResult

        data = {"statistics": {"avg": 50}, "field_name": "POP", "extra": True}
        result = SummaryResult.model_validate(data)
        dumped = result.model_dump()
        assert dumped["field_name"] == "POP"
        assert dumped["extra"] is True


# ---------------------------------------------------------------------------
# ConversationHistory — add_message / get_messages
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client with an in-memory list."""
    r = AsyncMock()
    _store = {}

    async def _rpush(key, *values):
        _store.setdefault(key, []).extend(values)

    async def _ltrim(key, start, stop):
        if key in _store:
            lst = _store[key]
            # Redis ltrim with negative indices
            _store[key] = lst[start:] if stop == -1 else lst[start:stop + 1]

    async def _lrange(key, start, stop):
        if key not in _store:
            return []
        lst = _store[key]
        if stop == -1:
            return lst[start:]
        return lst[start:stop + 1]

    async def _expire(key, ttl):
        pass

    r.rpush = AsyncMock(side_effect=_rpush)
    r.ltrim = AsyncMock(side_effect=_ltrim)
    r.lrange = AsyncMock(side_effect=_lrange)
    r.expire = AsyncMock(side_effect=_expire)
    return r


@pytest.mark.asyncio
async def test_add_message_stores_entry(mock_redis):
    """add_message stores a single role/content entry."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        result = await ConversationHistory.add_message("s1", "user", "show counties")

    assert result is True
    mock_redis.rpush.assert_called_once()
    args = mock_redis.rpush.call_args[0]
    assert args[0] == "hist:s1"
    entry = json.loads(args[1])
    assert entry["role"] == "user"
    assert entry["content"] == "show counties"


@pytest.mark.asyncio
async def test_add_message_assistant(mock_redis):
    """Assistant messages stored correctly."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        result = await ConversationHistory.add_message("s1", "assistant", "Found 58 counties")

    assert result is True
    args = mock_redis.rpush.call_args[0]
    entry = json.loads(args[1])
    assert entry["role"] == "assistant"


@pytest.mark.asyncio
async def test_add_message_redis_unavailable():
    """Returns False when Redis is None."""
    with patch("core.history.get_redis", return_value=None):
        from core.history import ConversationHistory

        result = await ConversationHistory.add_message("s1", "user", "test")

    assert result is False


@pytest.mark.asyncio
async def test_get_messages_within_budget(mock_redis):
    """get_messages returns messages within token budget."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        # Add several messages
        await ConversationHistory.add_message("s1", "user", "query 1")
        await ConversationHistory.add_message("s1", "assistant", "result 1")
        await ConversationHistory.add_message("s1", "user", "query 2")
        await ConversationHistory.add_message("s1", "assistant", "result 2")

        messages = await ConversationHistory.get_messages("s1", max_tokens=4000)

    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "query 1"
    assert messages[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_get_messages_trims_oldest(mock_redis):
    """get_messages trims oldest messages when budget exceeded."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        # Add messages that together exceed a tiny budget
        await ConversationHistory.add_message("s1", "user", "a " * 100)
        await ConversationHistory.add_message("s1", "assistant", "b " * 100)
        await ConversationHistory.add_message("s1", "user", "short")
        await ConversationHistory.add_message("s1", "assistant", "also short")

        # Very small budget — should only get the last few messages
        messages = await ConversationHistory.get_messages("s1", max_tokens=20)

    # The two short messages fit; the two long ones don't
    assert len(messages) < 4
    # Most recent messages retained
    assert messages[-1]["content"] == "also short"


@pytest.mark.asyncio
async def test_get_messages_empty_session(mock_redis):
    """Empty session returns empty list."""
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        messages = await ConversationHistory.get_messages("nonexistent", max_tokens=4000)

    assert messages == []


@pytest.mark.asyncio
async def test_get_messages_redis_unavailable():
    """Returns empty list when Redis is None."""
    with patch("core.history.get_redis", return_value=None):
        from core.history import ConversationHistory

        messages = await ConversationHistory.get_messages("s1", max_tokens=4000)

    assert messages == []


@pytest.mark.asyncio
async def test_add_turn_backward_compat(mock_redis):
    """Legacy add_turn still works."""
    plan = {"action": "query", "message": "test"}
    with patch("core.history.get_redis", return_value=mock_redis):
        from core.history import ConversationHistory

        result = await ConversationHistory.add_turn("s1", "show psap", plan)

    assert result is True
    mock_redis.rpush.assert_called_once()
