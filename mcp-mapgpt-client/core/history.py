"""
Conversation history — generic message storage per session with token-budget trimming.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import tiktoken

from core.config import settings
from core.redis_client import get_redis

logger = logging.getLogger(__name__)

MAX_TURNS = settings.max_history_turns
MAX_ENTRIES = MAX_TURNS * 2  # Each turn = 1 user + 1 assistant entry
TOKEN_LIMIT = 500
SESSION_TTL = settings.session_ttl_seconds

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
    async def add_message(
        session_id: str,
        role: str,
        content: str,
    ) -> bool:
        """Append a single message to history and trim to MAX_ENTRIES.

        Args:
            session_id: Session identifier.
            role: Message role (``"user"``, ``"assistant"``, ``"tool"``).
            content: Message content string.

        Returns:
            True on success, False if Redis unavailable.
        """
        r = await get_redis()
        if r is None:
            logger.warning("Redis unavailable — history not stored")
            return False

        key = f"hist:{session_id}"
        try:
            entry = json.dumps({"role": role, "content": content})
            await r.rpush(key, entry)
            await r.ltrim(key, -MAX_ENTRIES, -1)
            await r.expire(key, SESSION_TTL)
            return True
        except Exception as exc:
            logger.warning("History add_message failed: %s", exc)
            return False

    @staticmethod
    async def add_turn(
        session_id: str,
        user_query: str,
        plan_json: Dict[str, Any],
    ) -> bool:
        """Legacy wrapper — stores a user + assistant turn pair.

        Deprecated: Use ``add_message()`` instead.
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
            await r.ltrim(key, -MAX_ENTRIES, -1)
            await r.expire(key, SESSION_TTL)
            return True
        except Exception as exc:
            logger.warning("History add_turn failed: %s", exc)
            return False

    @staticmethod
    async def get_messages(
        session_id: str,
        max_tokens: int = 4000,
    ) -> List[Dict[str, str]]:
        """Retrieve history messages within a token budget.

        Returns the most recent messages that fit within ``max_tokens``,
        trimming oldest first.  Returns an empty list if Redis is
        unavailable or no history exists.

        Args:
            session_id: Session identifier.
            max_tokens: Maximum total tokens across all returned messages.

        Returns:
            List of ``{"role": str, "content": str}`` dicts, oldest first.
        """
        r = await get_redis()
        if r is None:
            return []

        key = f"hist:{session_id}"
        try:
            entries = await r.lrange(key, 0, -1)
            if not entries:
                return []

            messages = [json.loads(e) for e in entries]

            # Walk backwards, accumulating tokens until budget exhausted
            selected: List[Dict[str, str]] = []
            token_total = 0
            for msg in reversed(messages):
                msg_tokens = _count_tokens(msg.get("content", ""))
                if token_total + msg_tokens > max_tokens:
                    break
                selected.append(msg)
                token_total += msg_tokens

            # Return in chronological order
            selected.reverse()
            return selected
        except Exception as exc:
            logger.warning("History get_messages failed: %s", exc)
            return []

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
