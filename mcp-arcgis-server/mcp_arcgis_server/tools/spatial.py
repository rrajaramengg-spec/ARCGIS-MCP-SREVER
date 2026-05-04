"""
Spatial join and layer join tools for ArcGIS feature layers.

Tools: spatial_join_query, join_layers
"""

import logging
from typing import Annotated, Any, Dict, List

from pydantic import Field

from ..arcgis.client import ArcGISClient
from ..arcgis.geometry import union_feature_geometries
from ._registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="spatial_join_query",
    description=(
        "Perform a spatial join: query a boundary layer with a WHERE clause, "
        "automatically union ALL matching boundary feature geometries into a single "
        "polygon, then use the unified geometry as a spatial filter on a target layer. "
        "Supports both feature return and count-only modes. The geometry union is "
        "automatic — just provide the boundary WHERE clause and target layer URL."
    ),
)
async def spatial_join_query(
    client: ArcGISClient,
    boundary_layer_url: Annotated[str, Field(description="URL of the boundary layer to query geometry from")],
    boundary_where: Annotated[str, Field(description="SQL WHERE clause to select the boundary feature(s)")],
    target_layer_url: Annotated[str, Field(description="URL of the target layer to query with the spatial filter")],
    operation: Annotated[str, Field(description='Operation type: "where" to return features, "count" to return only the count')] = "where",
) -> Dict[str, Any]:
    """Perform a spatial join: query a boundary layer for geometry, then query a target layer.

    First queries the boundary layer to obtain geometry, then uses that geometry
    as a spatial filter on the target layer.
    """
    boundary_result = await client.query_layer(
        layer_url=boundary_layer_url,
        where=boundary_where,
        return_geometry=True,
        out_fields="*",
    )

    boundary_features = boundary_result.get("features", [])
    if not boundary_features:
        return {"error": "No boundary features found", "where": boundary_where}

    try:
        boundary_geometry = union_feature_geometries(boundary_features)
    except Exception as exc:
        logger.error(
            "Geometry union failed for boundary (%d features): %s",
            len(boundary_features), exc, exc_info=True,
        )
        return {
            "error": "Geometry union failed",
            "detail": str(exc) or "Could not union boundary geometries",
            "where": boundary_where,
        }

    if not boundary_geometry:
        return {"error": "Boundary features have no geometry", "where": boundary_where}

    if operation == "count":
        result = await client.query_layer(
            layer_url=target_layer_url,
            where="1=1",
            return_count_only=True,
            geometry=boundary_geometry,
            spatial_rel="esriSpatialRelIntersects",
        )
        return {"count": result.get("count", 0)}
    else:
        result = await client.spatial_query(
            layer_url=target_layer_url,
            geometry=boundary_geometry,
            spatial_rel="esriSpatialRelIntersects",
        )
        return result


@register_tool(
    name="join_layers",
    description="Join two ArcGIS feature layers on a shared attribute field.",
)
async def join_layers(
    client: ArcGISClient,
    primary_layer_url: Annotated[str, Field(description="URL of the primary layer")],
    primary_where: Annotated[str, Field(description="WHERE clause for the primary layer")] = "1=1",
    primary_fields: Annotated[str, Field(description="Fields to return from the primary layer")] = "*",
    secondary_layer_url: Annotated[str, Field(description="URL of the secondary layer")] = "",
    secondary_where: Annotated[str, Field(description="WHERE clause for the secondary layer")] = "1=1",
    secondary_fields: Annotated[str, Field(description="Fields to return from the secondary layer")] = "*",
    join_field: Annotated[str, Field(description="The attribute field name used to join features")] = "",
) -> Dict[str, Any]:
    """Join two ArcGIS feature layers on a shared attribute field.

    Queries both layers and performs a client-side attribute join,
    returning primary features enriched with matching secondary attributes.
    """
    primary_result = await client.query_layer(
        layer_url=primary_layer_url,
        where=primary_where,
        out_fields=primary_fields,
    )
    secondary_result = await client.query_layer(
        layer_url=secondary_layer_url,
        where=secondary_where,
        out_fields=secondary_fields,
    )

    primary_features = primary_result.get("features", [])
    secondary_features = secondary_result.get("features", [])

    secondary_lookup: Dict[Any, Dict[str, Any]] = {}
    for feat in secondary_features:
        key = feat.get("attributes", {}).get(join_field)
        if key is not None:
            secondary_lookup[key] = feat

    joined: List[Dict[str, Any]] = []
    for feat in primary_features:
        join_value = feat.get("attributes", {}).get(join_field)
        if join_value in secondary_lookup:
            merged = {
                "attributes": {
                    **feat.get("attributes", {}),
                    **secondary_lookup[join_value].get("attributes", {}),
                },
                "geometry": feat.get("geometry"),
            }
            joined.append(merged)

    return {
        "type": "joined_features",
        "features": joined,
        "count": len(joined),
    }
