"""Alembic env.py — async PostgreSQL migration configuration.

Reads the database URL from ``config.settings.settings.pg_dsn`` and uses
``infrastructure.database.connection.Base.metadata`` for autogenerate support.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

# Ensure project root is on sys.path for config.settings import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import settings

# ── Alembic config object
config = context.config

# ── Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import models so Base.metadata is populated ─────────────────────────
# This MUST happen before accessing target_metadata.
from infrastructure.database import models  # noqa: E402, F401
from infrastructure.database.connection import Base  # noqa: E402

target_metadata = Base.metadata


# ── Only track tables in our metadata; ignore LangGraph checkpointer tables
def include_name(name: str, type_: str, parent_names: dict) -> bool:
    if type_ == "table":
        return name in target_metadata.tables
    return True


# ── Override sqlalchemy.url from settings ─────────────────────────────
config.set_main_option("sqlalchemy.url", settings.pg_dsn)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Execute migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with an async engine."""
    connectable = create_async_engine(
        settings.pg_dsn,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
