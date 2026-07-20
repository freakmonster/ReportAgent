"""Database initialization — PostgreSQL schema setup.

Creates LangGraph checkpointer tables (via raw DDL) and runs Alembic
migrations for all application tables.

Usage:
    python scripts/init_db.py --dsn postgresql://postgres:postgres@localhost:5432/research_agent
"""

from __future__ import annotations

import argparse
import subprocess
import sys

# LangGraph checkpointer tables — managed by the library's AsyncPostgresSaver.setup().
# We keep the raw DDL as a fallback for environments where setup() hasn't been called.
CHECKPOINT_DDL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_checkpoint_thread ON checkpoints(thread_id, checkpoint_ns);
"""

# ── Application tables DDL (managed outside Alembic for direct deployment) ──

APP_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
    title VARCHAR(200),
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    report_count INT NOT NULL DEFAULT 0,
    first_query TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    model VARCHAR(32) NOT NULL,
    request_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,
    prompt_tokens BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    estimated_cost_usd NUMERIC(10,4) DEFAULT 0,
    avg_duration_ms FLOAT DEFAULT 0,
    p50_duration_ms FLOAT DEFAULT 0,
    p95_duration_ms FLOAT DEFAULT 0,
    UNIQUE (date, model)
);

CREATE TABLE IF NOT EXISTS workflow_info (
    workflow_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    template_name TEXT NOT NULL DEFAULT 'deep_report',
    status TEXT NOT NULL DEFAULT 'init',
    retry_count INTEGER NOT NULL DEFAULT 0,
    quality_score FLOAT DEFAULT 0.0,
    session_id VARCHAR(36),
    started_at TIMESTAMPTZ,
    duration_seconds FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE workflow_info
    ADD COLUMN IF NOT EXISTS session_id VARCHAR(36);
"""


def _create_checkpoint_tables(dsn: str) -> bool:
    """Create LangGraph checkpointer tables via asyncpg raw DDL."""
    try:
        import asyncio

        import asyncpg

        async def _run() -> None:
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute(CHECKPOINT_DDL)
                print("[OK] Checkpointer tables created")
            finally:
                await conn.close()

        asyncio.run(_run())
        return True
    except ImportError:
        print("[WARN] asyncpg not installed. Install with: pip install asyncpg")
        print("[INFO] Run this SQL manually to create checkpointer tables:")
        print(CHECKPOINT_DDL)
        return False
    except Exception as exc:
        print(f"[FAIL] Checkpointer table creation failed: {exc}", file=sys.stderr)
        return False


def _create_app_tables(dsn: str) -> bool:
    """Create application tables (sessions) and apply schema migrations via raw DDL."""
    try:
        import asyncio

        import asyncpg

        async def _run() -> None:
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute(APP_TABLE_DDL)
                print("[OK] Application tables created / migrated")
            finally:
                await conn.close()

        asyncio.run(_run())
        return True
    except ImportError:
        print("[WARN] asyncpg not installed. Install with: pip install asyncpg")
        print("[INFO] Run this SQL manually to create application tables:")
        print(APP_TABLE_DDL)
        return False
    except Exception as exc:
        print(f"[FAIL] Application table creation failed: {exc}", file=sys.stderr)
        return False


def _run_alembic() -> bool:
    """Run Alembic migrations for all application tables."""
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=None,  # uses current working directory
        )
        if result.returncode == 0:
            return True
        print(f"[FAIL] Alembic failed:\n{result.stderr}", file=sys.stderr)
    except FileNotFoundError:
        print(
            "[FAIL] Alembic not found. Install with: pip install alembic",
            file=sys.stderr,
        )
    except Exception as exc:
        print(f"[FAIL] Alembic error: {exc}", file=sys.stderr)
    return False


def init_db(dsn: str = "") -> bool:
    """Initialize database schema.

    1. Creates LangGraph checkpointer tables (raw DDL)
    2. Runs Alembic migrations for all application tables

    Args:
        dsn: PostgreSQL connection string.
             Defaults to postgresql://postgres:postgres@localhost:5432/research_agent

    Returns:
        True if all steps succeeded.
    """
    if not dsn:
        dsn = "postgresql://postgres:postgres@localhost:5432/research_agent"

    print(f"--- Init DB: {dsn} ---")

    # Step 1: Checkpointer tables (raw DDL)
    checkpointer_ok = _create_checkpoint_tables(dsn)

    # Step 2: Application tables (raw DDL — sessions, workflow_info migration)
    app_ok = _create_app_tables(dsn)

    # Step 3: Alembic migrations (workflow_info, workflow_states, index_status, etc.)
    alembic_ok = _run_alembic()

    if checkpointer_ok and app_ok and alembic_ok:
        print("[OK] Database initialized successfully")
        return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize research_agent database")
    parser.add_argument("--dsn", default="", help="PostgreSQL connection string")
    args = parser.parse_args()
    success = init_db(args.dsn)
    sys.exit(0 if success else 1)
