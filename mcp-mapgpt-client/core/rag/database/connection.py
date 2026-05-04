"""
Database connection for the RAG module.
Provides async engine and session factory initialised from DATABASE_URL.
"""

import logging
import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Module-level singletons — initialised by init_db()
engine: AsyncEngine = None  # type: ignore[assignment]
_session_factory: async_sessionmaker[AsyncSession] = None  # type: ignore[assignment]


def async_session_factory() -> AsyncSession:
    """Return a new async session. Requires init_db() to have been called."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _session_factory()


def init_db() -> None:
    """Initialise the async engine and session factory from DATABASE_URL.

    Must be called once at application startup before any RAG functions.
    """
    global engine, _session_factory

    database_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://mapgpt:mapgpt@postgres:5432/mapgpt"
    )

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
    )

    _session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    logger.info("RAG database initialised — %s", database_url.split("@")[-1])


async def close_db() -> None:
    """Dispose of the engine and release connections."""
    if engine:
        await engine.dispose()
        logger.info("RAG database connections closed")
