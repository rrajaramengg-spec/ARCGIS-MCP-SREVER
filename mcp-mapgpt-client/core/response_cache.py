"""
Feedback-driven response cache — Redis-backed with promoted-entry eviction protection.
"""

import json
import logging
from typing import Any, Dict, Optional

from core.config import settings
from core.redis_client import get_redis

logger = logging.getLogger(__name__)

SESSION_TTL = settings.session_ttl_seconds
DEFAULT_CACHE_TTL = 86400  # 1 day
PROMOTED_CACHE_TTL = 864000  # 10 days


class ResponseCache:
    """Cross-session response cache in Redis under ``fcache:`` prefix.

    Stores JSON hash with ``response`` (serialized ExecuteResponse) and
    ``promoted`` (boolean flag for eviction protection).
    """

    @staticmethod
    def _cache_key(normalized_query: str, context_hash: str) -> str:
        return f"fcache:{normalized_query}:{context_hash}"

    @staticmethod
    async def get(
        normalized_query: str, context_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Look up a cached response. Returns None on miss or Redis unavailable."""
        r = await get_redis()
        if r is None:
            return None

        key = ResponseCache._cache_key(normalized_query, context_hash)
        try:
            data = await r.hget(key, "response")
            if data is None:
                return None
            return json.loads(data)
        except Exception as exc:
            logger.warning("Cache get failed: %s", exc)
            return None

    @staticmethod
    async def set(
        normalized_query: str,
        context_hash: str,
        response: Dict[str, Any],
        ttl: int = DEFAULT_CACHE_TTL,
    ) -> bool:
        """Store a response in cache with default TTL. Returns True on success."""
        r = await get_redis()
        if r is None:
            return False

        key = ResponseCache._cache_key(normalized_query, context_hash)
        try:
            payload = {
                "response": json.dumps(response),
                "promoted": "false",
            }
            await r.hset(key, mapping=payload)
            await r.expire(key, ttl)
            return True
        except Exception as exc:
            logger.warning("Cache set failed: %s", exc)
            return False

    @staticmethod
    async def promote(cache_key: str, ttl: int = PROMOTED_CACHE_TTL) -> bool:
        """Set promoted=true and extend TTL. Returns True on success."""
        r = await get_redis()
        if r is None:
            return False

        try:
            await r.hset(cache_key, "promoted", "true")
            await r.expire(cache_key, ttl)
            return True
        except Exception as exc:
            logger.warning("Cache promote failed: %s", exc)
            return False

    @staticmethod
    async def evict(cache_key: str) -> str:
        """Evict a cache entry if not promoted.

        Returns:
            "evicted" — entry deleted
            "protected" — entry is promoted, not deleted
            "no_cache_entry" — key does not exist
        """
        r = await get_redis()
        if r is None:
            return "no_cache_entry"

        try:
            promoted = await r.hget(cache_key, "promoted")
            if promoted is None:
                return "no_cache_entry"
            if promoted == "true":
                logger.info("Cache entry protected from eviction: %s", cache_key)
                return "protected"
            await r.delete(cache_key)
            return "evicted"
        except Exception as exc:
            logger.warning("Cache evict failed: %s", exc)
            return "no_cache_entry"

    @staticmethod
    async def store_query_mapping(
        session_id: str,
        query_id: str,
        cache_key: str,
    ) -> bool:
        """Store qmap:{session_id}:{query_id} → cache_key for feedback linkage."""
        r = await get_redis()
        if r is None:
            return False

        key = f"qmap:{session_id}:{query_id}"
        try:
            await r.set(key, cache_key, ex=SESSION_TTL)
            return True
        except Exception as exc:
            logger.warning("Query mapping store failed: %s", exc)
            return False

    @staticmethod
    async def get_cache_key_for_query(
        session_id: str, query_id: str
    ) -> Optional[str]:
        """Look up the cache key for a query_id via the qmap mapping."""
        r = await get_redis()
        if r is None:
            return None

        key = f"qmap:{session_id}:{query_id}"
        try:
            return await r.get(key)
        except Exception as exc:
            logger.warning("Query mapping lookup failed: %s", exc)
            return None
