"""Repository for tracking vector-index build status in PostgreSQL.

Stores one row per Qdrant collection so that index-rebuild orchestrators
and query services can coordinate without race conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional

from sqlalchemy import (
    func,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import select

from infrastructure.database.models import index_status

# ── Types ──────────────────────────────────────────────────────────────

IndexStatus = Literal["ready", "building", "failed"]


# ── Record ─────────────────────────────────────────────────────────────


@dataclass
class IndexStatusRecord:
    """Deserialised row from the ``index_status`` table."""

    collection_name: str
    status: IndexStatus
    error_msg: Optional[str]
    checksum: Optional[str]  # hash of source documents at build time
    document_count: int
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> IndexStatusRecord:
        """Build a record from a SQLAlchemy Row / mapping."""
        return cls(
            collection_name=row.collection_name,
            status=row.status,
            error_msg=row.error_msg,
            checksum=row.checksum,
            document_count=row.document_count,
            updated_at=row.updated_at,
        )


# ── Repository ─────────────────────────────────────────────────────────


class IndexRepository:
    """Async repository for the ``index_status`` table.

    Uses SQLAlchemy Core (no ORM models).  The caller must supply the same
    ``async_sessionmaker[AsyncSession]`` factory that the application uses
    for all database access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Read ──────────────────────────────────────────────────────────

    async def get_status(self, collection_name: str) -> Optional[IndexStatusRecord]:
        """Return the status record for *collection_name*, or ``None``."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(index_status).where(
                    index_status.c.collection_name == collection_name
                )
            )
            row = result.first()
            if row is None:
                return None
            return IndexStatusRecord.from_row(row)

    # ── Upsert ────────────────────────────────────────────────────────

    async def upsert_status(self, record: IndexStatusRecord) -> None:
        """Insert or replace (on conflict by *collection_name*) a status row."""
        async with self._session_factory() as session:
            stmt = (
                pg_insert(index_status)
                .values(
                    collection_name=record.collection_name,
                    status=record.status,
                    error_msg=record.error_msg,
                    checksum=record.checksum,
                    document_count=record.document_count,
                    updated_at=datetime.utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=["collection_name"],
                    set_={
                        "status": pg_insert.excluded.status,
                        "error_msg": pg_insert.excluded.error_msg,
                        "checksum": pg_insert.excluded.checksum,
                        "document_count": pg_insert.excluded.document_count,
                        "updated_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    # ── Convenience helpers ───────────────────────────────────────────

    async def mark_building(self, collection_name: str) -> None:
        """Shortcut: mark *collection_name* as ``'building'`` (clears previous error)."""
        async with self._session_factory() as session:
            stmt = (
                pg_insert(index_status)
                .values(
                    collection_name=collection_name,
                    status="building",
                    error_msg=None,
                    document_count=0,
                    updated_at=datetime.utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=["collection_name"],
                    set_={
                        "status": "building",
                        "error_msg": None,
                        "document_count": 0,
                        "updated_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def mark_ready(
        self, collection_name: str, document_count: int, checksum: str
    ) -> None:
        """Shortcut: mark *collection_name* as ``'ready'`` after a successful build."""
        async with self._session_factory() as session:
            stmt = (
                pg_insert(index_status)
                .values(
                    collection_name=collection_name,
                    status="ready",
                    error_msg=None,
                    checksum=checksum,
                    document_count=document_count,
                    updated_at=datetime.utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=["collection_name"],
                    set_={
                        "status": "ready",
                        "error_msg": None,
                        "checksum": checksum,
                        "document_count": document_count,
                        "updated_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def mark_failed(self, collection_name: str, error_msg: str) -> None:
        """Shortcut: mark *collection_name* as ``'failed'`` with an error message."""
        async with self._session_factory() as session:
            stmt = (
                pg_insert(index_status)
                .values(
                    collection_name=collection_name,
                    status="failed",
                    error_msg=error_msg,
                    document_count=0,
                    updated_at=datetime.utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=["collection_name"],
                    set_={
                        "status": "failed",
                        "error_msg": error_msg,
                        "document_count": 0,
                        "updated_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()


# ── Singleton ──────────────────────────────────────────────────────────

_index_repo: IndexRepository | None = None


def init_index_repo(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Initialise the index repository singleton.

    Must be called during app startup (after ``init_db()``).
    """
    global _index_repo
    _index_repo = IndexRepository(session_factory)


def get_index_repo() -> IndexRepository:
    """Return the index repository singleton.

    Raises ``RuntimeError`` if ``init_index_repo()`` was not called first.
    """
    if _index_repo is None:
        raise RuntimeError(
            "IndexRepository not initialised. Call init_index_repo() first."
        )
    return _index_repo
