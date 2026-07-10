"""Repository for reading/writing LangGraph State via PostgreSQL.

Provides optimistic-locking helpers to prevent double-submit of human-in-the-loop
review actions (approve / reject).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import select, update

# ── Schema ─────────────────────────────────────────────────────────────

metadata = MetaData()

workflow_states = Table(
    "workflow_states",
    metadata,
    Column("workflow_id", String, primary_key=True),
    Column("status", String, nullable=False, default="init"),
    Column("state_data", JSONB, nullable=False),
    Column("user_id", String, nullable=False),
    Column("template_name", String, nullable=False),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
)


# ── Record ─────────────────────────────────────────────────────────────


@dataclass
class WorkflowStateRecord:
    """Deserialised row from the ``workflow_states`` table."""

    workflow_id: str
    status: str  # init | collecting | writing | reviewing | pending | approved | rejected | published
    state_data: dict[str, Any]  # serialized LangGraph State
    user_id: str
    template_name: str
    retry_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> WorkflowStateRecord:
        """Build a record from a SQLAlchemy Row / mapping."""
        return cls(
            workflow_id=row.workflow_id,
            status=row.status,
            state_data=row.state_data or {},
            user_id=row.user_id,
            template_name=row.template_name,
            retry_count=row.retry_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# ── Repository ─────────────────────────────────────────────────────────


class WorkflowRepository:
    """Async repository for the ``workflow_states`` table.

    Uses SQLAlchemy Core (no ORM models).  The caller must supply the same
    ``async_sessionmaker[AsyncSession]`` factory that the application uses
    for all database access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Read ──────────────────────────────────────────────────────────

    async def get_by_id(self, workflow_id: str) -> Optional[WorkflowStateRecord]:
        """Return a single workflow record by its primary key, or ``None``."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(workflow_states).where(workflow_states.c.workflow_id == workflow_id)
            )
            row = result.first()
            if row is None:
                return None
            return WorkflowStateRecord.from_row(row)

    async def list_pending(self) -> list[WorkflowStateRecord]:
        """Return all workflows currently waiting for human review (status = 'pending')."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(workflow_states)
                .where(workflow_states.c.status == "pending")
                .order_by(workflow_states.c.updated_at.asc())
            )
            return [WorkflowStateRecord.from_row(r) for r in result.fetchall()]

    # ── Write (upsert) ─────────────────────────────────────────────────

    async def save(self, record: WorkflowStateRecord) -> None:
        """Insert a new workflow record or update an existing one (upsert by workflow_id)."""
        async with self._session_factory() as session:
            stmt = (
                pg_insert(workflow_states)
                .values(
                    workflow_id=record.workflow_id,
                    status=record.status,
                    state_data=record.state_data,
                    user_id=record.user_id,
                    template_name=record.template_name,
                    retry_count=record.retry_count,
                    created_at=record.created_at,
                    updated_at=datetime.utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=["workflow_id"],
                    set_={
                        "status": pg_insert.excluded.status,
                        "state_data": pg_insert.excluded.state_data,
                        "user_id": pg_insert.excluded.user_id,
                        "template_name": pg_insert.excluded.template_name,
                        "retry_count": pg_insert.excluded.retry_count,
                        "updated_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    # ── Human-review actions (optimistic locking) ──────────────────────

    async def approve_with_lock(self, workflow_id: str) -> bool:
        """Approve a pending workflow using optimistic locking.

        Executes ``UPDATE … WHERE workflow_id=$1 AND status='pending'`` so
        that **only one** human-review action can succeed per review cycle.

        Returns:
            ``True`` if exactly one row was updated, ``False`` if the
            workflow was already acted upon (409-conflict scenario).
        """
        async with self._session_factory() as session:
            result = await session.execute(
                update(workflow_states)
                .where(
                    workflow_states.c.workflow_id == workflow_id,
                    workflow_states.c.status == "pending",
                )
                .values(status="approved", updated_at=func.now())
            )
            await session.commit()
            return result.rowcount == 1

    async def reject_with_lock(self, workflow_id: str, reason: str) -> bool:
        """Reject a pending workflow using optimistic locking.

        The rejection reason is merged into the ``state_data`` JSONB column
        so downstream consumers can surface it to the user.

        Returns:
            ``True`` if exactly one row was updated, ``False`` if the
            workflow was already acted upon (409-conflict scenario).
        """
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    UPDATE workflow_states
                    SET status       = 'rejected',
                        state_data   = state_data || :reason_json ::jsonb,
                        updated_at   = NOW()
                    WHERE workflow_id = :workflow_id
                      AND status      = 'pending'
                    """
                ),
                {
                    "workflow_id": workflow_id,
                    "reason_json": f'{{"rejection_reason": "{reason}"}}',
                },
            )
            await session.commit()
            return result.rowcount == 1
