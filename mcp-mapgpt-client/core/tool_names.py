"""Single source of truth for MCP tool name constants.

All tool name strings used across the client codebase MUST be imported
from this module — no inline string literals elsewhere.
"""

from typing import FrozenSet

# ---------------------------------------------------------------------------
# Individual tool name constants
# ---------------------------------------------------------------------------

QUERY_FEATURES = "query_features"
COUNT_FEATURES = "count_features"
SPATIAL_JOIN_QUERY = "spatial_join_query"
JOIN_LAYERS = "join_layers"
EXECUTE_QUERY_PLAN = "execute_query_plan"
SEARCH_CONTENT = "search_content"
SEARCH_LAYERS = "search_layers"
SUMMARIZE_FIELD = "summarize_field"
GET_FEATURE_TABLE = "get_feature_table"
BUFFER_AND_QUERY = "buffer_and_query"
FIND_NEARBY = "find_nearby"
GEOCODE = "geocode"
REVERSE_GEOCODE = "reversegeocode"
UNION_GEOMETRIES = "union_geometries"

# ---------------------------------------------------------------------------
# Aggregate set — used for semaphore / validation checks
# ---------------------------------------------------------------------------

ARCGIS_TOOL_NAMES: FrozenSet[str] = frozenset(
    {
        QUERY_FEATURES,
        COUNT_FEATURES,
        SPATIAL_JOIN_QUERY,
        JOIN_LAYERS,
        EXECUTE_QUERY_PLAN,
        SEARCH_CONTENT,
        SEARCH_LAYERS,
        SUMMARIZE_FIELD,
        GET_FEATURE_TABLE,
        BUFFER_AND_QUERY,
        FIND_NEARBY,
        GEOCODE,
        REVERSE_GEOCODE,
        UNION_GEOMETRIES,
    }
)
