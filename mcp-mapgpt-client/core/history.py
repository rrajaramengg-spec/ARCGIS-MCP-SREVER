"""
Conversation history — last-3-turns storage per session with tiktoken-based plan trimming.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import tiktoken

from core.redis_client import get_redis

logger = logging.getLogger(__name__)

MAX_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "3"))
MAX_ENTRIES = MAX_TURNS * 2  # Each turn = 1 user + 1 assistant entry
TOKEN_LIMIT = 500
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "7200"))

_encoding: Optional[tiktoken.Encoding] = None


def _get_encoding() -> tiktoken.Encoding:
    """Lazy-load the tiktoken encoding."""
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("o200k_base")
    return _encoding


def _count_tokens(text: str) -> int:
    """Count tokens in text using o200k_base encoding."""
    return len(_get_encoding().encode(text))


def _trim_plan(plan: Dict[str, Any]) -> str:
    """Token-trim a plan dict and return as JSON string.

    Trimming priority (when over TOKEN_LIMIT):
    1. Strip ``layer_url`` values (LLM re-derives from RAG)
    2. Strip ``fields`` arrays
    3. Strip verbose ``where`` clauses (replace with placeholder)

    Preserved fields: action, type, layer, where, children, message, join_type.
    """
    plan_json = json.dumps(plan, separators=(",", ":"))
    if _count_tokens(plan_json) <= TOKEN_LIMIT:
        return plan_json

    # Pass 1: Strip layer_url values
    trimmed = _strip_field_recursive(plan, "layer_url")
    plan_json = json.dumps(trimmed, separators=(",", ":"))
    if _count_tokens(plan_json) <= TOKEN_LIMIT:
        return plan_json

    # Pass 2: Strip fields arrays
    trimmed = _strip_field_recursive(trimmed, "fields")
    plan_json = json.dumps(trimmed, separators=(",", ":"))
    if _count_tokens(plan_json) <= TOKEN_LIMIT:
        return plan_json

    # Pass 3: Truncate long where clauses
    trimmed = _truncate_where_recursive(trimmed)
    plan_json = json.dumps(trimmed, separators=(",", ":"))
    return plan_json


def _strip_field_recursive(obj: Any, field_name: str) -> Any:
    """Recursively remove a field from dicts and lists of dicts."""
    if isinstance(obj, dict):
        return {
            k: _strip_field_recursive(v, field_name)
            for k, v in obj.items()
            if k != field_name
        }
    if isinstance(obj, list):
        return [_strip_field_recursive(item, field_name) for item in obj]
    return obj


def _truncate_where_recursive(obj: Any, max_len: int = 80) -> Any:
    """Recursively truncate long 'where' clause values."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k == "where" and isinstance(v, str) and len(v) > max_len:
                result[k] = v[:max_len] + "..."
            else:
                result[k] = _truncate_where_recursive(v, max_len)
        return result
    if isinstance(obj, list):
        return [_truncate_where_recursive(item, max_len) for item in obj]
    return obj


class ConversationHistory:
    """Manages per-session conversation history in Redis under ``hist:{session_id}``."""

    @staticmethod
    async def add_turn(
        session_id: str,
        user_query: str,
        plan_json: Dict[str, Any],
    ) -> bool:
        """Append a user/assistant turn to history and trim to MAX_TURNS.

        Returns True on success, False if Redis unavailable.
        """
        r = await get_redis()
        if r is None:
            logger.warning("Redis unavailable — history not stored")
            return False

        key = f"hist:{session_id}"
        try:
            user_entry = json.dumps({"role": "user", "content": user_query})
            assistant_content = _trim_plan(plan_json)
            assistant_entry = json.dumps(
                {"role": "assistant", "content": assistant_content}
            )

            await r.rpush(key, user_entry, assistant_entry)
            # Trim to keep only last MAX_ENTRIES (oldest entries removed)
            await r.ltrim(key, -MAX_ENTRIES, -1)
            await r.expire(key, SESSION_TTL)
            return True
        except Exception as exc:
            logger.warning("History add_turn failed: %s", exc)
            return False

    @staticmethod
    async def get_turns(session_id: str) -> List[Dict[str, Any]]:
        """Retrieve all history entries for a session in chronological order.

        Returns an empty list if Redis is unavailable or no history exists.
        """
        r = await get_redis()
        if r is None:
            return []

        key = f"hist:{session_id}"
        try:
            entries = await r.lrange(key, 0, -1)
            return [json.loads(e) for e in entries]
        except Exception as exc:
            logger.warning("History get_turns failed: %s", exc)
            return []
