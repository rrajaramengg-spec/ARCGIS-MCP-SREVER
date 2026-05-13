"""
Geocoding tools for ArcGIS — forward and reverse geocode.

Tools: geocode, reverse_geocode
"""

import logging
from typing import Annotated, Any, Dict

from pydantic import Field

from ..arcgis.client import ArcGISClient
from ._registry import register_tool

logger = logging.getLogger(__name__)

MAX_GEOCODE_RESULTS = 10


@register_tool(
    name="geocode",
    description="Geocode an address to geographic coordinates.",
)
async def geocode(
    client: ArcGISClient,
    address: Annotated[str, Field(description="Address string to geocode")],
    max_results: Annotated[int, Field(description="Maximum number of candidates to return (max 10)")] = 5,
    out_sr: Annotated[int, Field(description="Output spatial reference WKID (default WGS84)")] = 4326,
) -> Dict[str, Any]:
    """Geocode an address to geographic coordinates.

    Converts an address string to one or more geographic coordinate candidates
    with match scores. Requires authenticated GIS instance.
    """
    if not address or not address.strip():
        return {"error": "Invalid input", "detail": "Address must not be empty"}

    effective_max = min(max_results, MAX_GEOCODE_RESULTS)

    try:
        candidates = await client.geocode(
            address=address, max_results=effective_max, out_sr=out_sr,
        )
        return {
            "candidates": candidates, "count": len(candidates), "query": address,
        }
    except RuntimeError as e:
        return {"error": "GIS not authenticated", "detail": str(e)}
    except Exception as e:
        logger.error("geocode error: %s", e, exc_info=True)
        return {"error": "geocode failed", "detail": str(e)}


@register_tool(
    name="reversegeocode",
    description="Reverse geocode coordinates to an address.",
)
async def reverse_geocode(
    client: ArcGISClient,
    latitude: Annotated[float, Field(description="Latitude in WGS84 (-90 to 90)")],
    longitude: Annotated[float, Field(description="Longitude in WGS84 (-180 to 180)")],
    distance: Annotated[float, Field(description="Search radius in meters for finding the nearest address")] = 100,
) -> Dict[str, Any]:
    """Reverse geocode coordinates to an address.

    Converts geographic coordinates to a street address with components.
    Requires authenticated GIS instance.
    """
    if not (-90 <= latitude <= 90):
        return {
            "error": "Invalid latitude",
            "detail": "Latitude must be between -90 and 90",
        }
    if not (-180 <= longitude <= 180):
        return {
            "error": "Invalid longitude",
            "detail": "Longitude must be between -180 and 180",
        }

    try:
        result = await client.reverse_geocode(
            latitude=latitude, longitude=longitude, distance=distance,
        )
        return result
    except RuntimeError as e:
        return {"error": "GIS not authenticated", "detail": str(e)}
    except Exception as e:
        logger.error("reverse_geocode error: %s", e, exc_info=True)
        return {"error": "reverse_geocode failed", "detail": str(e)}
