"""
LocateHandler — direct geocoding without LLM planning.
Extracts locate() from the monolithic orchestrator.
"""

import json
import logging
import re
import time
from typing import Any, Dict, Optional

from .base import BaseHandler, register_handler

logger = logging.getLogger(__name__)


@register_handler("locate", prefix="/locate ")
class LocateHandler(BaseHandler):
    """Handles direct geocoding via MCP tools (no LLM planning)."""

    async def locate(
        self,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Direct geocoding — address string or lat/lon coordinates.

        Returns:
            LocateResponse-shaped dict.
        """
        start = time.perf_counter()

        # Detect coordinate pattern in address string (e.g., "39.7,-104.9")
        if address and latitude is None and longitude is None:
            coord_match = re.match(
                r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", address
            )
            if coord_match:
                latitude = float(coord_match.group(1))
                longitude = float(coord_match.group(2))
                address = None

        # When address is provided, prefer it over zero-valued coordinates
        if address and latitude is not None and longitude is not None:
            if latitude == 0 and longitude == 0:
                latitude = None
                longitude = None

        if latitude is not None and longitude is not None:
            tool_name = "reverse_geocode"
            tool_args: Dict[str, Any] = {"latitude": latitude, "longitude": longitude}
        elif address:
            tool_name = "geocode"
            tool_args = {"address": address}
        else:
            total_ms = (time.perf_counter() - start) * 1000
            return {
                "action": "locate",
                "location": None,
                "address": None,
                "candidates": None,
                "score": None,
                "execution_time_ms": round(total_ms, 2),
                "timing": self.build_timing(total_ms=0),
            }

        tool_start = time.perf_counter()
        try:
            logger.info("Direct locate — tool=%s args=%s", tool_name, tool_args)
            _cb = getattr(self, '_progress_callback', None)
            result = await self._mcp.call_tool(
                tool_name, tool_args,
                **({'progress_callback': _cb} if _cb is not None else {})
            )
        except Exception as exc:
            logger.error("Locate tool %s failed: %s", tool_name, exc)
            total_ms = (time.perf_counter() - start) * 1000
            return {
                "action": "locate",
                "location": None,
                "address": None,
                "candidates": None,
                "score": None,
                "execution_time_ms": round(total_ms, 2),
                "timing": self.build_timing(tool_ms=(time.perf_counter() - tool_start) * 1000),
            }
        tool_ms = (time.perf_counter() - tool_start) * 1000

        # Parse result from MCP tool
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass

        location = None
        resolved_address = None
        candidates = None
        score = None

        if isinstance(result, dict):
            # Check for error response
            if result.get("error"):
                error_msg = result.get("error")
                detail = result.get("detail", "")
                logger.error("Locate tool returned error: %s — %s", error_msg, detail)
                total_ms = (time.perf_counter() - start) * 1000
                return {
                    "action": "locate",
                    "location": None,
                    "address": None,
                    "candidates": None,
                    "score": None,
                    "error": f"{error_msg}: {detail}" if detail else error_msg,
                    "execution_time_ms": round(total_ms, 2),
                    "timing": self.build_timing(tool_ms=tool_ms),
                }

            # geocode returns candidates list; reverse_geocode returns address info
            candidates = result.get("candidates")
            if candidates and isinstance(candidates, list) and len(candidates) > 0:
                top = candidates[0]
                location = top.get("location")
                resolved_address = top.get("address")
                score = top.get("score")
            else:
                location = result.get("location")
                resolved_address = result.get("address")
                score = result.get("score")

        total_ms = (time.perf_counter() - start) * 1000
        return {
            "action": "locate",
            "location": location,
            "address": resolved_address,
            "candidates": candidates,
            "score": score,
            "execution_time_ms": round(total_ms, 2),
            "timing": self.build_timing(tool_ms=tool_ms),
        }
