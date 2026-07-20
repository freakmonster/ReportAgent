"""SQLAlchemy Table definitions — single source of truth for Alembic migrations.

All tables use ``connection.Base.metadata``, enabling Alembic autogenerate
to detect schema changes automatically.

Tables:
    workflow_info    — workflow metadata (status tracking)
    workflow_states  — LangGraph state snapshots (for human-in-the-loop)
    index_status     — vector-index build status per Qdrant collection

Note:
    LangGraph checkpointer tables (checkpoints, checkpoint_blobs, checkpoint_writes)
    are managed by ``AsyncPostgresSaver.setup()`` and are NOT included here.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from infrastructure.database.connection import Base

# ── Tables ───────────────────────────────────────────────────────────────

workflow_info = Table(
    "workflow_info",
    Base.metadata,
    Column("workflow_id", Text, primary_key=True),
    Column("user_id", Text, nullable=False),
    Column("template_name", Text, nullable=False, default="deep_report"),
    Column("status", Text, nullable=False, default="init"),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("quality_score", Float, default=0.0),
    Column("session_id", String(36), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("duration_seconds", Float, default=0.0),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    # Indexes
    Index("idx_workflow_user", "user_id"),
    Index("idx_workflow_status", "status"),
    Index("idx_workflow_created", "created_at"),
)

workflow_states = Table(
    "workflow_states",
    Base.metadata,
    Column("workflow_id", Text, primary_key=True),
    Column("status", Text, nullable=False, default="init"),
    Column("state_data", JSONB, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("template_name", Text, nullable=False),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

index_status = Table(
    "index_status",
    Base.metadata,
    Column("collection_name", Text, primary_key=True),
    Column("status", Text, nullable=False, default="building"),
    Column("error_msg", Text, nullable=True),
    Column("checksum", Text, nullable=True),
    Column("document_count", Integer, nullable=False, default=0),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

sessions = Table(
    "sessions",
    Base.metadata,
    Column("session_id", String(36), primary_key=True),
    Column("user_id", String(64), nullable=False),
    Column("tenant_id", String(64), nullable=False, server_default="default"),
    Column("title", String(200), nullable=True),
    Column("status", String(16), nullable=False, server_default="active"),
    Column("report_count", Integer, nullable=False, server_default="0"),
    Column("first_query", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

usage_daily = Table(
    "usage_daily",
    Base.metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False),
    Column("model", String(32), nullable=False),
    Column("request_count", Integer, nullable=False, server_default="0"),
    Column("success_count", Integer, nullable=False, server_default="0"),
    Column("total_tokens", BigInteger, nullable=False, server_default="0"),
    Column("prompt_tokens", BigInteger, nullable=False, server_default="0"),
    Column("completion_tokens", BigInteger, nullable=False, server_default="0"),
    Column("estimated_cost_usd", Numeric(10, 4), nullable=False, server_default="0"),
    Column("avg_duration_ms", Float, nullable=False, server_default="0"),
    Column("p50_duration_ms", Float, nullable=False, server_default="0"),
    Column("p95_duration_ms", Float, nullable=False, server_default="0"),
    UniqueConstraint("date", "model"),
)

# ── Export list ──────────────────────────────────────────────────────────

__all__ = [
    "workflow_info",
    "workflow_states",
    "index_status",
    "sessions",
    "usage_daily",
]
