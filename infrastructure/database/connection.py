"""SQLAlchemy async engine and session management for PostgreSQL."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from config.settings import settings

# ── Declarative Base ────────────────────────────────────────
Base = declarative_base()

# Import models so their metadata is registered on Base BEFORE create_tables() runs.
# This ensures ``Base.metadata.create_all`` and Alembic autogenerate see all tables.
from infrastructure.database import models  # noqa: E402, F401

# ── Engine ──────────────────────────────────────────────────
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """Initialize the async engine and session factory."""
    global _engine, _async_session_factory

    _engine = create_async_engine(
        settings.pg_dsn,
        pool_size=20,
        max_overflow=10,
        pool_recycle=3600,
        echo=settings.debug,
    )

    _async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def close_db() -> None:
    """Dispose the engine and release all connections."""
    global _engine, _async_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _async_session_factory is None:
        raise RuntimeError(
            "Database not initialised. Call init_db() before using get_db()."
        )
    return _async_session_factory


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding a database session.

    Rolls back on exception and always closes the session.
    """
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def create_tables() -> None:
    """Create all tables declared via Base.metadata."""
    if _engine is None:
        raise RuntimeError(
            "Database not initialised. Call init_db() before create_tables()."
        )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
