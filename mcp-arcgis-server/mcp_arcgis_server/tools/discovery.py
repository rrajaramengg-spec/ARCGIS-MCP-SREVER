"""
Content discovery tools for ArcGIS portal and server.

Tools: search_content, search_layers
"""

import logging
from typing import Annotated, Any, Dict, Optional

from pydantic import Field

from ..arcgis.client import ArcGISClient
from ._registry import register_tool

logger = logging.getLogger(__name__)

MAX_SEARCH_ITEMS = 50


@register_tool(
    name="search_content",
    description="Search ArcGIS portal/server for content items by keyword and type.",
)
async def search_content(
    client: ArcGISClient,
    query: Annotated[str, Field(description="Search keyword(s) for portal content")],
    item_type: Annotated[Optional[str], Field(description="Filter by item type, e.g. 'Feature Layer', 'Map Service'")] = None,
    max_items: Annotated[int, Field(description="Maximum number of results to return (max 50)")] = 10,
) -> Dict[str, Any]:
    """Search ArcGIS portal/server for content items by keyword and type.

    Returns a list of matching content items with metadata including title,
    type, URL, owner, and description. Requires authenticated GIS instance.
    """
    if not query or not query.strip():
        return {"error": "Invalid input", "detail": "Query string must not be empty"}

    effective_max = min(max_items, MAX_SEARCH_ITEMS)
    capped = max_items > MAX_SEARCH_ITEMS

    try:
        items = await client.search_content(
            query=query, item_type=item_type, max_items=effective_max,
        )
        result: Dict[str, Any] = {
            "items": items, "count": len(items), "query": query,
        }
        if capped:
            result["capped"] = True
        return result
    except RuntimeError as e:
        return {"error": "GIS not authenticated", "detail": str(e)}
    except Exception as e:
        logger.error("search_content error: %s", e, exc_info=True)
        return {"error": "search_content failed", "detail": str(e)}


@register_tool(
    name="search_layers",
    description="Discover available feature layers on an ArcGIS Server or portal.",
)
async def search_layers(
    client: ArcGISClient,
    service_url: Annotated[Optional[str], Field(description="ArcGIS Server REST endpoint URL (MapServer or FeatureServer)")] = None,
    query: Annotated[Optional[str], Field(description="Keyword to search portal for feature layers")] = None,
) -> Dict[str, Any]:
    """Discover available feature layers on an ArcGIS Server or portal.

    Provide either a service URL to list its layers, or a keyword to search
    the portal for feature layers. At least one parameter must be provided.
    """
    if not service_url and not query:
        return {
            "error": "Invalid input",
            "detail": "At least one of service_url or query must be provided",
        }

    if service_url:
        try:
            layers = await client.get_service_layers(service_url)
            return {
                "layers": layers, "count": len(layers),
                "source": "service_url", "service_url": service_url,
            }
        except RuntimeError as e:
            return {"error": "GIS not authenticated", "detail": str(e)}
        except Exception as e:
            logger.error("search_layers error: %s", e, exc_info=True)
            return {"error": "search_layers failed", "detail": str(e)}
    else:
        try:
            items = await client.search_content(
                query=query, item_type="Feature Layer", max_items=MAX_SEARCH_ITEMS,
            )
            return {
                "layers": items, "count": len(items),
                "source": "portal_search", "query": query,
            }
        except RuntimeError as e:
            return {"error": "GIS not authenticated", "detail": str(e)}
        except Exception as e:
            logger.error("search_layers error: %s", e, exc_info=True)
            return {"error": "search_layers failed", "detail": str(e)}
