"""
Field summarization and feature table tools for ArcGIS feature layers.

Tools: summarize_field, get_feature_table
"""

import logging
from typing import Annotated, Any, Dict, List, Optional

from pydantic import Field

from ..arcgis.client import ArcGISClient, MAX_RESULT_COUNT
from ._registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="summarize_field",
    description="Compute field statistics or unique values for a feature layer field.",
)
async def summarize_field(
    client: ArcGISClient,
    layer_url: Annotated[str, Field(description="Full URL to the ArcGIS feature layer endpoint")],
    field_name: Annotated[str, Field(description="Name of the field to summarize")],
    where: Annotated[str, Field(description="SQL WHERE clause to filter features before summarization")] = "1=1",
    statistics: Annotated[Optional[str], Field(description="Comma-separated list of statistics: count,min,max,avg,stddev (numeric fields only)")] = None,
) -> Dict[str, Any]:
    """Compute field statistics or unique values for a feature layer field.

    For numeric fields: returns count, min, max, avg, stddev, and null_count.
    For string fields: returns unique values with counts, sorted by frequency.
    """
    stats_list = None
    if statistics:
        stats_list = [s.strip() for s in statistics.split(",")]

    try:
        layer_info = await client.get_layer_info(layer_url)
        fields = layer_info.get("fields", [])

        field_info = None
        for f in fields:
            if f.get("name", "").upper() == field_name.upper():
                field_info = f
                break

        if field_info is None:
            return {
                "error": "Invalid field",
                "detail": f"Field '{field_name}' not found on layer",
            }

        field_type = field_info.get("type", "")
        actual_name = field_info.get("name", field_name)

        if "String" in field_type:
            unique_values = await client.get_unique_values(
                layer_url=layer_url, field_name=actual_name,
                where=where, max_values=100,
            )
            unique_values.sort(key=lambda v: v.get("count", 0), reverse=True)
            return {
                "field": actual_name, "type": field_type,
                "unique_values": unique_values,
                "distinct_count": len(unique_values),
            }

        if stats_list is None:
            stats_list = ["count", "min", "max", "avg", "stddev"]

        stats = await client.get_field_statistics(
            layer_url=layer_url, field_name=actual_name,
            statistics=stats_list, where=where,
        )

        result_stats = {}
        for stat in stats_list:
            key = f"{stat}_{actual_name}"
            result_stats[stat] = stats.get(key)

        null_stats = await client.get_field_statistics(
            layer_url=layer_url, field_name=actual_name,
            statistics=["count"],
            where=f"({where}) AND {actual_name} IS NULL",
        )
        null_count = null_stats.get(f"count_{actual_name}", 0)

        return {
            "field": actual_name, "type": field_type,
            "statistics": result_stats, "null_count": null_count,
        }

    except Exception as e:
        logger.error("summarize_field error: %s", e, exc_info=True)
        return {"error": "summarize_field failed", "detail": str(e)}


@register_tool(
    name="get_feature_table",
    description="Retrieve a formatted feature table from a feature layer in JSON or markdown format.",
)
async def get_feature_table(
    client: ArcGISClient,
    layer_url: Annotated[str, Field(description="Full URL to the ArcGIS feature layer endpoint")],
    where: Annotated[str, Field(description="SQL WHERE clause to filter features")] = "1=1",
    fields: Annotated[str, Field(description="Comma-separated list of fields to return, or '*' for all")] = "*",
    max_records: Annotated[int, Field(description="Maximum number of records to return (max 200)")] = 50,
    format: Annotated[str, Field(description="Output format: 'json' for structured data, 'markdown' for formatted table")] = "json",
) -> Dict[str, Any]:
    """Retrieve a formatted feature table from a feature layer.

    Returns feature data optimized for LLM consumption in JSON (columns + rows)
    or markdown table format. Records are capped at 200.
    """
    effective_max = min(max_records, MAX_RESULT_COUNT)
    truncated = max_records > MAX_RESULT_COUNT

    try:
        result = await client.query_layer(
            layer_url=layer_url, where=where, out_fields=fields,
            return_geometry=False, result_record_count=effective_max,
        )

        features = result.get("features", [])
        if not features:
            layer_info = await client.get_layer_info(layer_url)
            column_names = [f.get("name") for f in layer_info.get("fields", [])]
            if fields != "*":
                requested = [f.strip() for f in fields.split(",")]
                column_names = [c for c in column_names if c in requested]
            return {"columns": column_names, "rows": [], "count": 0, "total_count": 0}

        first_attrs = features[0].get("attributes", {})
        columns = list(first_attrs.keys())

        rows = [
            [f.get("attributes", {}).get(col) for col in columns]
            for f in features
        ]

        count_result = await client.query_layer(
            layer_url=layer_url, where=where, return_count_only=True,
        )
        total_count = count_result.get("count", len(rows))

        if format == "markdown":
            header = "| " + " | ".join(str(c) for c in columns) + " |"
            separator = "| " + " | ".join("---" for _ in columns) + " |"
            data_rows = [
                "| " + " | ".join(str(v) if v is not None else "" for v in row) + " |"
                for row in rows
            ]
            table = "\n".join([header, separator] + data_rows)
            response: Dict[str, Any] = {
                "table": table, "count": len(rows), "total_count": total_count,
            }
        else:
            response = {
                "columns": columns, "rows": rows,
                "count": len(rows), "total_count": total_count,
            }

        if truncated:
            response["truncated"] = True
        return response

    except Exception as e:
        logger.error("get_feature_table error: %s", e, exc_info=True)
        return {"error": "get_feature_table failed", "detail": str(e)}
