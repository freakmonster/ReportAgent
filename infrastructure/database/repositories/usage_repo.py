"""Repository for usage statistics and admin dashboard aggregation queries.

Queries ``usage_daily`` and ``workflow_info`` tables to provide
high-level usage overviews and recent workflow activity for the
admin dashboard.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import select

from infrastructure.database.models import usage_daily, workflow_info


class UsageRepository:
    """Async repository for usage / dashboard aggregation queries.

    Uses SQLAlchemy Core (no ORM models), following the same pattern
    as ``WorkflowRepository``.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Aggregation ────────────────────────────────────────────────────

    async def get_overview(self, days: int = 7) -> dict[str, Any]:
        """Aggregate overview data from ``usage_daily`` and ``workflow_info``.

        Returns:
            dict with keys: total_requests, success_rate, total_tokens,
            avg_duration_seconds, by_template.
            Returns zeros / empty dict when no data is present.
        """
        cutoff_dt = datetime.utcnow() - timedelta(days=days)
        cutoff_date = cutoff_dt.date()

        async with self._session_factory() as session:
            # ── usage_daily ─────────────────────────────────────────
            usage_row = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(usage_daily.c.request_count), 0).label(
                            "total_requests"
                        ),
                        func.coalesce(func.sum(usage_daily.c.total_tokens), 0).label(
                            "total_tokens"
                        ),
                    ).where(usage_daily.c.date >= cutoff_date)
                )
            ).first()

            # ── workflow_info ───────────────────────────────────────
            total_count = (
                await session.scalar(
                    select(func.count())
                    .select_from(workflow_info)
                    .where(workflow_info.c.created_at >= cutoff_dt)
                )
            ) or 0

            success_count = (
                await session.scalar(
                    select(func.count())
                    .select_from(workflow_info)
                    .where(
                        workflow_info.c.created_at >= cutoff_dt,
                        workflow_info.c.status == "published",
                    )
                )
            ) or 0

            avg_dur_row = (
                await session.execute(
                    select(
                        func.avg(
                            func.extract(
                                "epoch",
                                workflow_info.c.updated_at - workflow_info.c.created_at,
                            )
                        )
                    ).where(workflow_info.c.created_at >= cutoff_dt)
                )
            ).first()

            avg_duration = (
                float(avg_dur_row[0]) if avg_dur_row and avg_dur_row[0] else 0.0
            )

            # by_template: grouped by template_name
            template_rows = (
                await session.execute(
                    select(
                        workflow_info.c.template_name,
                        func.count().label("count"),
                        func.avg(
                            func.extract(
                                "epoch",
                                workflow_info.c.updated_at - workflow_info.c.created_at,
                            )
                        ).label("avg_duration"),
                    )
                    .where(workflow_info.c.created_at >= cutoff_dt)
                    .group_by(workflow_info.c.template_name)
                )
            ).fetchall()

            by_template: dict[str, dict[str, Any]] = {}
            for row in template_rows:
                by_template[row.template_name] = {
                    "count": row.count,
                    "avg_duration": round(float(row.avg_duration), 2)
                    if row.avg_duration
                    else 0.0,
                }

            return {
                "total_requests": int(usage_row.total_requests) if usage_row else 0,
                "success_rate": round(success_count / total_count, 4)
                if total_count > 0
                else 0.0,
                "total_tokens": int(usage_row.total_tokens) if usage_row else 0,
                "avg_duration_seconds": round(avg_duration, 2),
                "by_template": by_template,
            }

    # ── Recent activity ────────────────────────────────────────────────

    async def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent N entries from ``workflow_info``.

        Returns:
            List of dicts with keys: workflow_id, user_id, template_name,
            status, duration_ms, created_at.  Empty list when no data.
        """
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        workflow_info.c.workflow_id,
                        workflow_info.c.user_id,
                        workflow_info.c.template_name,
                        workflow_info.c.status,
                        func.extract(
                            "epoch",
                            workflow_info.c.updated_at - workflow_info.c.created_at,
                        ).label("duration_seconds"),
                        workflow_info.c.created_at,
                    )
                    .order_by(workflow_info.c.created_at.desc())
                    .limit(limit)
                )
            ).fetchall()

            return [
                {
                    "workflow_id": row.workflow_id,
                    "user_id": row.user_id,
                    "template_name": row.template_name,
                    "status": row.status,
                    "duration_ms": round(float(row.duration_seconds) * 1000, 0)
                    if row.duration_seconds
                    else 0,
                    "created_at": row.created_at.isoformat()
                    if row.created_at
                    else None,
                }
                for row in rows
            ]


# ── Singleton ──────────────────────────────────────────────────────────

_usage_repo: UsageRepository | None = None


def init_usage_repo(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Initialise the usage repository singleton.

    Must be called during app startup (after ``init_db()``).
    """
    global _usage_repo
    _usage_repo = UsageRepository(session_factory)


def get_usage_repo() -> UsageRepository:
    """Return the usage repository singleton.

    Raises ``RuntimeError`` if ``init_usage_repo()`` was not called first.
    """
    if _usage_repo is None:
        raise RuntimeError(
            "UsageRepository not initialised. Call init_usage_repo() first."
        )
    return _usage_repo
