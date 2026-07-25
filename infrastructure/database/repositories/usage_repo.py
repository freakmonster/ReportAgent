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

    # ── Write ──────────────────────────────────────────────────────────

    async def record_workflow_info(
        self,
        workflow_id: str,
        user_id: str,
        template_name: str,
        status: str = "published",
        session_id: str | None = None,
        started_at: float = 0.0,
        duration_seconds: float = 0.0,
        query: str = "",
        report_content: str = "",
        citations: list = None,
        charts: list = None,
    ) -> None:
        """Insert / upsert a workflow execution record into ``workflow_info``."""
        from datetime import datetime as _dt
        from datetime import timezone as _tz
        import json as _json
        from sqlalchemy import text

        citations_json = _json.dumps(citations or [], ensure_ascii=False)
        charts_json = _json.dumps(charts or [], ensure_ascii=False)

        async with self._session_factory() as session:
            await session.execute(
                text(
                    """INSERT INTO workflow_info
                    (workflow_id, user_id, template_name, status,
                     session_id, query, report_content, citations, charts,
                     started_at, duration_seconds, created_at, updated_at)
                    VALUES (:wid, :uid, :tmpl, :st, :sid, :q, :rc, :cit, :cht,
                            :sat, :dur, :now, :now)
                    ON CONFLICT (workflow_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        duration_seconds = EXCLUDED.duration_seconds,
                        updated_at = EXCLUDED.updated_at,
                        query = EXCLUDED.query,
                        report_content = EXCLUDED.report_content,
                        citations = EXCLUDED.citations,
                        charts = EXCLUDED.charts"""
                ),
                {
                    "wid": workflow_id,
                    "uid": user_id,
                    "tmpl": template_name,
                    "st": status,
                    "sid": session_id,
                    "q": query,
                    "rc": report_content,
                    "cit": citations_json,
                    "cht": charts_json,
                    "sat": _dt.fromtimestamp(started_at, tz=_tz.utc) if started_at else None,
                    "dur": duration_seconds,
                    "now": _dt.now(_tz.utc),
                },
            )
            await session.commit()
            print(
                f"[usage_repo] record_workflow_info | {workflow_id} status={status} template={template_name} dur={duration_seconds}s",
                flush=True,
            )

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
            # ── Diagnose: raw row count ──
            raw_count = await session.scalar(
                select(func.count()).select_from(workflow_info)
            )
            raw_in_window = await session.scalar(
                select(func.count()).select_from(workflow_info)
                .where(workflow_info.c.created_at >= cutoff_dt)
            )
            print(
                f"[dashboard] workflow_info total={raw_count} | in_window={raw_in_window} | days={days} | cutoff={cutoff_dt.isoformat()}",
                flush=True,
            )
            
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
                    select(func.avg(workflow_info.c.duration_seconds)).where(
                        workflow_info.c.created_at >= cutoff_dt
                    )
                )
            ).first()

            avg_duration = float(avg_dur_row[0]) if avg_dur_row and avg_dur_row[0] else 0.0

            # by_template: grouped by template_name
            template_rows = (
                await session.execute(
                    select(
                        workflow_info.c.template_name,
                        func.count().label("count"),
                        func.avg(workflow_info.c.duration_seconds).label("avg_duration"),
                    )
                    .where(workflow_info.c.created_at >= cutoff_dt)
                    .group_by(workflow_info.c.template_name)
                )
            ).fetchall()

            by_template: dict[str, dict[str, Any]] = {}
            for row in template_rows:
                by_template[row.template_name] = {
                    "count": row.count,
                    "avg_duration": round(float(row.avg_duration), 2) if row.avg_duration else 0.0,
                }

            result = {
                "total_requests": total_count,
                "success_rate": round(success_count / total_count, 4) if total_count > 0 else 0.0,
                # NOTE: total_tokens requires usage_daily populated by aggregate_daily_usage.py cron job
                "total_tokens": int(usage_row.total_tokens) if usage_row else 0,
                "avg_duration_seconds": round(avg_duration, 2),
                "by_template": by_template,
            }
            print(
                f"[dashboard] overview result | requests={result['total_requests']} "
                f"rate={result['success_rate']} tokens={result['total_tokens']} "
                f"avg_dur={result['avg_duration_seconds']}s templates={len(result['by_template'])}",
                flush=True,
            )
            return result

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
                        workflow_info.c.duration_seconds,
                        workflow_info.c.created_at,
                    )
                    .order_by(workflow_info.c.created_at.desc())
                    .limit(limit)
                )
            ).fetchall()

            return [
                {
                    "id": row.workflow_id,
                    "user_id": row.user_id,
                    "query": row.template_name,
                    "model": row.template_name,
                    "status": row.status,
                    "duration": round(float(row.duration_seconds), 1)
                    if row.duration_seconds
                    else 0,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
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
        raise RuntimeError("UsageRepository not initialised. Call init_usage_repo() first.")
    return _usage_repo
