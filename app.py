"""FastAPI application entry point for the 智能研报生成系统.

V2.3: Registers all routes, middleware, and lifecycle events.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import chat, health, task
from api.middlewares.request_log import RequestLogMiddleware
from api.middlewares.rate_limit import RateLimitMiddleware
from config.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events.

    V2.3: Critical infrastructure (PG/Redis/Qdrant) loaded eagerly.
    Startup failure → sys.exit(1) to prevent serving incomplete state.
    """
    logger.info("app.starting", environment=settings.environment)

    # ── Eager-load critical infrastructure ──────────────────────────
    ok = True

    # PostgreSQL
    try:
        from infrastructure.database.connection import engine
        async with engine.begin() as conn:
            await conn.execute_text("SELECT 1")
        logger.info("lifespan.postgresql.connected", dsn=settings.pg_dsn[:20] + "...")
    except Exception as exc:
        logger.critical("lifespan.postgresql.failed", error=str(exc))
        ok = False

    # Redis (local service, independently managed)
    try:
        from infrastructure.cache.redis_client import RedisClient
        client = RedisClient()
        await client.ping()
        logger.info("lifespan.redis.connected", host=settings.redis_host)
    except Exception as exc:
        logger.warning(
            "lifespan.redis.unavailable",
            error=str(exc),
            hint="Redis is a local service. Start it manually if needed for rate-limit/supervisor.",
        )
        # Redis is non-critical: app can run without rate limiting

    # Qdrant
    try:
        from infrastructure.vector_db.qdrant_client import QdrantClient
        client = QdrantClient()
        # Qdrant health check: list collections
        await client.list_collections()
        logger.info("lifespan.qdrant.connected", url=settings.qdrant_url)
    except Exception as exc:
        logger.critical("lifespan.qdrant.failed", error=str(exc))
        ok = False

    if not ok:
        logger.critical(
            "lifespan.critical_failure",
            message="One or more critical services unavailable. Exiting.",
        )
        sys.exit(1)

    logger.info("lifespan.ready")
    yield
    logger.info("app.stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# ── Middleware (order matters: outer → inner) ─────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=settings.rate_limit_requests, window_seconds=settings.rate_limit_window)

# ── Routers ───────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(task.router)

# ── Main entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=settings.host, port=settings.port, reload=settings.debug)
