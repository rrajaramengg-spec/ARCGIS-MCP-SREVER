"""Typed result models for graph node executors.

Each executor validates its MCP tool output via ``{Model}.model_validate(raw)``.
``extra="allow"`` gives Pydantic type safety while tolerating ArcGIS schema
variance across server versions.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class FeatureSetResult(BaseModel):
    """Result from query, spatial_join, or proximity executors."""

    model_config = ConfigDict(extra="allow")

    features: List[Dict[str, Any]] = []
    count: int = 0
    geometryType: Optional[str] = None
    spatialReference: Optional[Dict[str, Any]] = None
    fields: Optional[List[Dict[str, Any]]] = None


class GeocodeResult(BaseModel):
    """Result from geocode executor."""

    model_config = ConfigDict(extra="allow")

    candidates: List[Dict[str, Any]] = []
    location: Optional[Dict[str, Any]] = None


class CountResult(BaseModel):
    """Result from count executor."""

    model_config = ConfigDict(extra="allow")

    count: int = 0


class BufferResult(BaseModel):
    """Result from buffer executor."""

    model_config = ConfigDict(extra="allow")

    buffer_geometry: Dict[str, Any] = {}


class SummaryResult(BaseModel):
    """Result from summarize executor."""

    model_config = ConfigDict(extra="allow")

    statistics: Dict[str, Any] = {}
    field_name: str = ""
