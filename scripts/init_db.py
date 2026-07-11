"""Database initialization — PostgreSQL schema setup for LangGraph checkpoint storage.

Creates the required tables for:
- LangGraph checkpoint states (checkpoint, checkpoint_blobs, checkpoint_writes)
- Workflow metadata (workflow_info) with status enumeration and indexes
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

SCHEMA_SQL = """
-- LangGraph Checkpointer tables (standard schema)
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

-- Workflow metadata table
CREATE TABLE IF NOT EXISTS workflow_info (
    workflow_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    template_name TEXT NOT NULL DEFAULT 'deep_report',
    status TEXT NOT NULL DEFAULT 'init'
        CHECK (status IN ('init','collecting','writing','reviewing','approved','rejected','published')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    quality_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_workflow_user ON workflow_info(user_id);
CREATE INDEX IF NOT EXISTS idx_workflow_status ON workflow_info(status);
CREATE INDEX IF NOT EXISTS idx_workflow_created ON workflow_info(created_at);
CREATE INDEX IF NOT EXISTS idx_checkpoint_thread ON checkpoints(thread_id, checkpoint_ns);

-- Updated trigger
CREATE OR REPLACE FUNCTION update_workflow_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_workflow_updated ON workflow_info;
CREATE TRIGGER trg_workflow_updated
    BEFORE UPDATE ON workflow_info
    FOR EACH ROW EXECUTE FUNCTION update_workflow_timestamp();
"""


def init_db(dsn: str = "") -> bool:
    """Initialize database schema.

    Args:
        dsn: PostgreSQL connection string.
             Defaults to postgresql://postgres:postgres@localhost:5432/research_agent

    Returns:
        True if initialization succeeded.
    """
    if not dsn:
        dsn = "postgresql://postgres:postgres@localhost:5432/research_agent"

    try:
        import asyncpg
        import asyncio

        async def _run() -> None:
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute(SCHEMA_SQL)
                print(f"[OK] Database schema initialized at {dsn}")
            finally:
                await conn.close()

        asyncio.run(_run())
        return True
    except ImportError:
        print("[WARN] asyncpg not installed. Install with: pip install asyncpg")
        print(f"[INFO] Run this SQL manually against {dsn}:")
        print(SCHEMA_SQL)
        return False
    except Exception as exc:
        print(f"[FAIL] Database init failed: {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize research_agent database")
    parser.add_argument("--dsn", default="", help="PostgreSQL connection string")
    args = parser.parse_args()
    success = init_db(args.dsn)
    sys.exit(0 if success else 1)
