"""Repository for reading/writing session metadata via PostgreSQL.

Provides CRUD operations for the ``sessions`` table with soft-delete support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import select, update

from infrastructure.database.models import sessions

# ── Record ─────────────────────────────────────────────────────────────


@dataclass
class SessionRecord:
    """Deserialised row from the ``sessions`` table."""

    session_id: str
    user_id: str
    tenant_id: str = "default"
    title: Optional[str] = None
    status: str = "active"
    report_count: int = 0
    first_query: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: object) -> SessionRecord:
        """Build a record from a SQLAlchemy Row / mapping."""
        return cls(
            session_id=row.session_id,
            user_id=row.user_id,
            tenant_id=row.tenant_id or "default",
            title=row.title,
            status=row.status,
            report_count=row.report_count,
            first_query=row.first_query,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# ── Repository ─────────────────────────────────────────────────────────


class SessionRepository:
    """Async repository for the ``sessions`` table.

    Uses SQLAlchemy Core (no ORM models).  The caller must supply the same
    ``async_sessionmaker[AsyncSession]`` factory that the application uses
    for all database access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Create ────────────────────────────────────────────────────────

    async def create(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
        first_query: Optional[str] = None,
        tenant_id: str = "default",
    ) -> SessionRecord:
        """Insert a new session row and return the created record."""
        now = datetime.utcnow()
        async with self._session_factory() as session:
            await session.execute(
                sessions.insert().values(
                    session_id=session_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    title=title,
                    status="active",
                    report_count=0,
                    first_query=first_query,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        return SessionRecord(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            title=title,
            status="active",
            report_count=0,
            first_query=first_query,
            created_at=now,
            updated_at=now,
        )

    # ── Read ──────────────────────────────────────────────────────────

    async def get_by_id(self, session_id: str) -> Optional[SessionRecord]:
        """Return a single session record by its primary key, or ``None``."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(sessions).where(sessions.c.session_id == session_id)
            )
            row = result.first()
            if row is None:
                return None
            return SessionRecord.from_row(row)

    async def list_by_user(self, user_id: str) -> list[SessionRecord]:
        """Return all active sessions for a user, ordered by most recently updated."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(sessions)
                .where(
                    sessions.c.user_id == user_id,
                    sessions.c.status == "active",
                )
                .order_by(sessions.c.updated_at.desc())
            )
            return [SessionRecord.from_row(r) for r in result.fetchall()]

    # ── Soft-delete ───────────────────────────────────────────────────

    async def soft_delete(self, session_id: str) -> None:
        """Mark a session as deleted (status='deleted')."""
        async with self._session_factory() as session:
            await session.execute(
                update(sessions)
                .where(sessions.c.session_id == session_id)
                .values(status="deleted", updated_at=func.now())
            )
            await session.commit()

    # ── Increment ─────────────────────────────────────────────────────

    async def increment_report_count(self, session_id: str) -> None:
        """Increment ``report_count`` by 1 and touch ``updated_at``."""
        async with self._session_factory() as session:
            await session.execute(
                update(sessions)
                .where(sessions.c.session_id == session_id)
                .values(
                    report_count=sessions.c.report_count + 1,
                    updated_at=func.now(),
                )
            )
            await session.commit()


# ── Singleton ──────────────────────────────────────────────────────────

_session_repo: SessionRepository | None = None


def init_session_repo(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Initialise the session repository singleton.

    Must be called during app startup (after ``init_db()``).
    """
    global _session_repo
    _session_repo = SessionRepository(session_factory)


def get_session_repo() -> SessionRepository:
    """Return the session repository singleton.

    Raises ``RuntimeError`` if ``init_session_repo()`` was not called first.
    """
    if _session_repo is None:
        raise RuntimeError("SessionRepository not initialised. Call init_session_repo() first.")
    return _session_repo
