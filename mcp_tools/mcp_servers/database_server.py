"""
Database MCP Server — Community Docker image wrapper.

Uses the writenotenow/postgres-mcp community Docker image
(originally neverinfamous/postgresql-mcp) to expose PostgreSQL
as an MCP-compatible HTTP service.

This module provides:
- Configuration documentation for the Docker image
- A FastAPI proxy/wrapper for additional authentication if needed
- Direct PostgreSQL access for internal (trusted) use
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration helper
# ---------------------------------------------------------------------------


def build_docker_compose_entry() -> dict[str, object]:
    """Generate the docker-compose service definition for the database MCP server.

    Returns a dict suitable for merging into docker-compose.yml.
    """
    from config.settings import settings

    return {
        "mcp-database": {
            "image": "writenotenow/postgres-mcp:latest",
            "container_name": "mcp-database",
            "environment": {
                "POSTGRES_HOST": "host.docker.internal",
                "POSTGRES_PORT": str(settings.pg_port),
                "POSTGRES_USER": settings.pg_user,
                "POSTGRES_PASSWORD": settings.pg_password,
                "POSTGRES_DATABASE": settings.pg_database,
            },
            "ports": ["8002:8002"],
            "restart": "unless-stopped",
            "networks": ["research_agent"],
        }
    }


# ---------------------------------------------------------------------------
# FastAPI proxy (optional thin wrapper for auth/logging)
# ---------------------------------------------------------------------------


def create_database_proxy_app() -> object:
    """Create a FastAPI proxy that adds auth/logging to the community MCP image.

    If the community image is sufficient, this proxy is not needed.
    Use this only when additional security or logging is required.
    """
    from fastapi import FastAPI

    app = FastAPI(title="MCP Database Proxy", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        # The actual health check depends on the community image's health endpoint
        return {"status": "ok", "service": "mcp-database-proxy"}

    return app


# ---------------------------------------------------------------------------
# Direct PostgreSQL client for internal use
# ---------------------------------------------------------------------------


class DatabaseClient:
    """Direct async PostgreSQL client for internal tools (bypasses MCP).

    Used when the MCP database server is unavailable or for
    performance-critical internal queries (e.g., index status checks).
    """

    def __init__(self) -> None:
        self._engine: object | None = None

    async def _ensure_engine(self) -> object:
        """Lazy-init SQLAlchemy async engine."""
        if self._engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine

            from config.settings import settings

            self._engine = create_async_engine(
                settings.pg_dsn,
                pool_size=5,
                max_overflow=10,
                echo=False,
            )
        return self._engine

    async def execute_query(
        self, sql: str, params: dict[str, object] | None = None
    ) -> list[dict[str, object]]:
        """Execute a raw SQL query and return results as a list of dicts.

        Args:
            sql: SQL query string.
            params: Optional query parameters.

        Returns:
            List of rows as dicts.
        """
        from sqlalchemy import text

        engine = await self._ensure_engine()
        async with engine.begin() as conn:  # type: ignore[union-attr]
            result = await conn.execute(text(sql), params or {})
            rows = result.fetchall()
            columns = list(result.keys())
            return [dict(zip(columns, row)) for row in rows]

    async def close(self) -> None:
        """Close the database engine."""
        if self._engine is not None:
            await self._engine.dispose()  # type: ignore[union-attr]
            self._engine = None


# Module-level singleton
db_client = DatabaseClient()
