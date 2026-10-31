"""Database connection and session management."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import PoolPrePing, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def create_engine(database_url: str | None = None) -> AsyncEngine:
    """Create async SQLAlchemy engine with optimized settings."""
    settings = get_settings()
    url = database_url or str(settings.database_url)

    return create_async_engine(
        url,
        echo=settings.debug,
        pool_pre_ping=PoolPrePing,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
    )


# Global engine instance for dependency injection
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the global database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the global session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_connection() -> AsyncIterator[AsyncConnection]:
    """Context manager for direct database connections."""
    engine = get_engine()
    async with engine.connect() as connection:
        yield connection


async def check_database_connection() -> bool:
    """Check if database is accessible."""
    try:
        async with get_db_connection() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """Dispose the global engine and reset singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
