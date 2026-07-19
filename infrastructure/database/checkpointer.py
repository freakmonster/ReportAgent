"""Checkpointer factory — singleton AsyncPostgresSaver lifecycle."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from config.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_checkpointer() -> AsyncIterator[object]:
    """Async context manager that yields an AsyncPostgresSaver instance.

    Usage in app.py lifespan::

        async with create_checkpointer() as checkpointer:
            app.state.checkpointer = checkpointer
            yield  # keep alive for the app lifetime
            # context exit closes the connection pool

    Yields:
        AsyncPostgresSaver instance (ready with tables created).
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        logger.info(f"checkpointer.connecting dsn={_mask_dsn(settings.pg_dsn)}")

        # psycopg (used by langgraph) expects postgresql:// not postgresql+asyncpg://
        dsn = settings.pg_dsn.replace("+asyncpg", "")
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.setup()
            logger.info("checkpointer.ready")
            yield saver

    except Exception as exc:
        logger.error(f"checkpointer.failed: {exc}")
        if settings.environment == "production":
            raise
        # Dev mode: yield None so the app still starts
        yield None


def _mask_dsn(dsn: str) -> str:
    """Mask password in a PostgreSQL DSN for logging."""
    if "@" in dsn:
        before, after = dsn.split("@", 1)
        return before.split(":")[0] + ":***@" + after
    return dsn
