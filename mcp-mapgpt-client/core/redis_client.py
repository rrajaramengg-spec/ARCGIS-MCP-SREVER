"""
Shared async Redis connection pool (DB 0) with lazy init and graceful fallback.
"""

import logging
from typing import Optional

import redis.asyncio as aioredis

from core.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[aioredis.ConnectionPool] = None
_redis: Optional[aioredis.Redis] = None


async def get_redis() -> Optional[aioredis.Redis]:
    """Return a shared async Redis client, or None if unavailable.

    Lazily creates the connection pool on first call.
    """
    global _pool, _redis

    if _redis is not None:
        try:
            await _redis.ping()
            return _redis
        except Exception:
            logger.warning("Redis ping failed, attempting reconnect")
            _redis = None
            _pool = None

    redis_url = settings.redis_url
    try:
        _pool = aioredis.ConnectionPool.from_url(
            redis_url,
            decode_responses=True,
            max_connections=20,
        )
        _redis = aioredis.Redis(connection_pool=_pool)
        await _redis.ping()
        logger.info("Redis connection established: %s", redis_url)
        return _redis
    except Exception as exc:
        logger.warning("Redis unavailable (%s): %s", redis_url, exc)
        _redis = None
        _pool = None
        return None


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _pool, _redis
    if _redis:
        await _redis.aclose()
    if _pool:
        await _pool.aclose()
    _redis = None
    _pool = None
