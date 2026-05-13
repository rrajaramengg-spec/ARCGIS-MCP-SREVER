"""
Pydantic request/response models for the API.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecuteRequest(BaseModel):
    """Request model for the /execute and /query endpoints."""

    query: str = Field(..., description="Natural language query")
    session_id: Optional[str] = Field(None, description="Optional session identifier")


class QueryResponse(BaseModel):
    """Response model for the /query endpoint (planning only, no execution)."""

    action: str
    query: Optional[Any] = None
    join: Optional[Any] = None
    locate: Optional[Any] = None
    route: Optional[Any] = None
    message: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class ArcGISFeature(BaseModel):
    """A single ArcGIS feature with attributes and optional geometry."""

    attributes: Dict[str, Any] = Field(default_factory=dict, description="Feature attribute key-value pairs")
    geometry: Optional[Dict[str, Any]] = Field(None, description="Feature geometry (rings, paths, x/y, etc.)")


class ArcGISField(BaseModel):
    """ArcGIS field metadata."""

    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field type (e.g., esriFieldTypeString)")
    alias: Optional[str] = Field(None, description="Field display alias")


class ArcGISQueryResult(BaseModel):
    """ArcGIS REST API standard FeatureSet format.

    Uses camelCase keys matching the ArcGIS REST API query response convention.
    Accepts both camelCase (from ArcGIS) and snake_case (Pythonic) field names.
    """

    model_config = ConfigDict(populate_by_name=True)

    features: List[ArcGISFeature] = Field(default_factory=list, description="List of features returned")
    count: int = Field(0, description="Number of features returned")
    object_id_field_name: Optional[str] = Field(None, alias="objectIdFieldName", description="Name of the Object ID field")
    geometry_type: Optional[str] = Field(None, alias="geometryType", description="Geometry type (e.g., esriGeometryPolygon)")
    spatial_reference: Optional[Dict[str, Any]] = Field(None, alias="spatialReference", description="Spatial reference (e.g., {wkid: 4326})")
    fields: Optional[List[ArcGISField]] = Field(None, description="Field definitions with names, types, and aliases")


class ExecuteResponse(BaseModel):
    """Response model for the /execute endpoint (actual ArcGIS execution).

    Graph path populates ``results`` (typed feature_set/geocode dicts).
    LLM paths (execute-llm, arcgis-execute) populate ``data``/``tool_name``/``tool_args``.
    """

    action: str
    message: Optional[str] = None
    data: Optional[Any] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Typed result array (feature_set/geocode dicts with role field)")
    execution_time_ms: float
    timing: Optional[Dict[str, float]] = Field(None, description="Per-phase timing breakdown (ms)")
    query_id: Optional[str] = Field(None, description="Unique query ID for feedback linkage")
    execution_graph: Optional[Dict[str, Any]] = Field(None, description="Graph execution metadata (when graph runtime used)")


class SummarizeResponse(BaseModel):
    """Response model for the /summarize endpoint."""

    action: str
    summary: str
    feature_count: int
    execution_time_ms: float
    timing: Optional[Dict[str, float]] = Field(None, description="Per-phase timing breakdown (ms)")


class IngestRequest(BaseModel):
    """Request model for the /ingest endpoint."""

    doc_type: str = Field(
        ..., description="Document type: 'layer' or 'query_pattern'"
    )
    data: List[Dict[str, Any]] = Field(
        ..., description="Array of objects to ingest"
    )
    replace: bool = Field(
        False, description="If True, clear existing data before ingesting (query_pattern only)"
    )


class IngestResponse(BaseModel):
    """Response model for the /ingest endpoint."""

    status: str
    layers: Optional[int] = None
    fields: Optional[int] = None
    patterns: Optional[int] = None


class HealthResponse(BaseModel):
    """Response model for /health."""


class LocateRequest(BaseModel):
    """Request model for the /locate endpoint."""

    address: Optional[str] = Field(None, description="Address to geocode")
    latitude: Optional[float] = Field(None, description="Latitude for reverse geocoding")
    longitude: Optional[float] = Field(None, description="Longitude for reverse geocoding")

    @model_validator(mode="after")
    def require_address_or_coordinates(self) -> "LocateRequest":
        has_address = self.address is not None
        has_coords = self.latitude is not None and self.longitude is not None
        if not has_address and not has_coords:
            raise ValueError("Either 'address' or both 'latitude' and 'longitude' are required")
        return self


class LocateResponse(BaseModel):
    """Response model for the /locate endpoint."""

    action: str = "locate"
    location: Optional[Dict[str, Any]] = Field(None, description="Location coordinates {x, y}")
    address: Optional[str] = Field(None, description="Resolved address")
    candidates: Optional[List[Dict[str, Any]]] = Field(None, description="Geocode candidates")
    score: Optional[float] = Field(None, description="Match score")
    execution_time_ms: float
    timing: Optional[Dict[str, float]] = Field(None, description="Per-phase timing breakdown (ms)")


class SummarizeStatResponse(BaseModel):
    """Response model for the /summarize-stat endpoint."""

    action: str = "summarize_stat"
    summary: str
    statistics: Optional[Dict[str, Any]] = Field(None, description="Field statistics from summarize_field")
    field_name: Optional[str] = Field(None, description="Field that was summarized")
    layer_url: Optional[str] = Field(None, description="Layer URL that was queried")
    feature_count: int = 0
    execution_time_ms: float
    timing: Optional[Dict[str, float]] = Field(None, description="Per-phase timing breakdown (ms)")

    status: str
    version: str = "1.0.0"
    detail: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Request model for the /user-feedback endpoint."""

    session_id: str = Field(..., description="Session identifier")
    query_id: str = Field(..., description="Query identifier for feedback linkage")
    feedback: Literal["up", "down"] = Field(..., description="Feedback type: 'up' or 'down'")


class FeedbackResponse(BaseModel):
    """Response model for the /user-feedback endpoint."""

    status: str = Field("ok", description="Request status")
    action: str = Field(..., description="Action taken: 'promoted', 'evicted', 'protected', or 'no_cache_entry'")
