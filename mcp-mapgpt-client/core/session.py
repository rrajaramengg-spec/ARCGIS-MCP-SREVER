"""
Session management — Redis-backed session store with sliding TTL.
"""

import logging
import os
import time
from typing import Optional

from core.redis_client import get_redis

logger = logging.getLogger(__name__)

SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "7200"))


class SessionManager:
    """Manages session lifecycle in Redis DB 0 under key prefix ``sess:``."""

    @staticmethod
    async def ensure_session(session_id: str) -> bool:
        """Create session if absent, refresh TTL on every call.

        Returns True if session was touched successfully, False if Redis unavailable.
        """
        r = await get_redis()
        if r is None:
            logger.warning("Redis unavailable — session not tracked")
            return False

        key = f"sess:{session_id}"
        try:
            exists = await r.exists(key)
            if not exists:
                await r.hset(key, "created_at", str(time.time()))
                logger.info("Session created: %s", session_id)
            await r.expire(key, SESSION_TTL)
            return True
        except Exception as exc:
            logger.warning("Session ensure failed: %s", exc)
            return False
