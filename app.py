"""FastAPI application entry point for the 智能研报生成系统.

V2.3: Registers all routes, middleware, and lifecycle events.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middlewares.auth import AuthMiddleware
from api.middlewares.rate_limit import RateLimitMiddleware
from api.middlewares.request_log import RequestLogMiddleware
from api.routers import admin, chat, health, index, task
from api.routers.session import router as session_router
from config.settings import settings
from infrastructure.database.checkpointer import create_checkpointer
from infrastructure.message_queue.dlq import init_dead_letter_queue
from infrastructure.message_queue.task_queue import init_task_queue
from infrastructure.observability.logger import get_logger
from infrastructure.observability.metrics import init_metrics
from infrastructure.observability.tracer import init_tracer, shutdown_tracer

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown.

    In dev mode: warns on connection failures, serves anyway.
    In prod mode: critical failure → sys.exit(1).
    """
    logger.info("app.starting", environment=settings.environment)

    critical_failures = 0

    # PostgreSQL
    try:
        from sqlalchemy import text

        from infrastructure.database.connection import _get_session_factory, get_db, init_db

        await init_db()
        async with get_db() as session:
            await session.execute(text("SELECT 1"))
        # Initialise workflow repository singleton
        from infrastructure.database.repositories.workflow_repo import (
            init_workflow_repo,
        )

        init_workflow_repo(_get_session_factory())
        # Initialise session repository singleton
        from infrastructure.database.repositories.session_repo import (
            init_session_repo,
        )

        init_session_repo(_get_session_factory())
        # Initialise usage repository singleton
        from infrastructure.database.repositories.usage_repo import (
            init_usage_repo,
        )

        init_usage_repo(_get_session_factory())
        logger.info("lifespan.postgresql.connected")
    except Exception as exc:
        critical_failures += 1
        _handle_startup_error("postgresql", exc)

    # Redis
    try:
        from infrastructure.cache.redis_client import get_redis, init_redis

        await init_redis()
        await get_redis().ping()
        logger.info("lifespan.redis.connected")
    except Exception as exc:
        if "HELLO" in str(exc):
            # Redis 5.x doesn't support RESP3 HELLO handshake;
            # the client falls back to RESP2 and basic operations still work
            logger.warning("lifespan.redis.resp3_unavailable (Redis < 6.0) — basic commands OK")
        else:
            _handle_startup_error("redis", exc)

    # Message queues (Redis Streams)
    try:
        from infrastructure.cache.redis_client import get_redis as _get_redis

        redis = _get_redis()
        init_task_queue(redis)
        init_dead_letter_queue(redis)
        logger.info("lifespan.message_queues.ready")
    except Exception as exc:
        logger.warning("lifespan.message_queues.failed | %s", exc)

    # Qdrant
    try:
        from infrastructure.vector_db.qdrant_client import get_qdrant, init_qdrant

        await init_qdrant()
        await get_qdrant().get_collections()
        logger.info("lifespan.qdrant.connected")
    except Exception as exc:
        critical_failures += 1
        _handle_startup_error("qdrant", exc)

    if critical_failures > 0 and settings.environment == "prod":
        logger.critical("lifespan.emergency_shutdown", failures=critical_failures)
        sys.exit(1)

    # OpenTelemetry Tracing
    try:
        init_tracer()
        logger.info("lifespan.tracer.initialized")
    except Exception as exc:
        logger.warning("lifespan.tracer.failed", detail=str(exc))

    # Prometheus Metrics (port=0 = don't start separate server; /metrics route in FastAPI)
    try:
        init_metrics(port=0)
        logger.info("lifespan.metrics.initialized")
    except Exception as exc:
        logger.warning("lifespan.metrics.failed", detail=str(exc))

    # Harness Orchestrator (governance handler chain)
    try:
        from harness.orchestrator.main import HarnessOrchestrator

        app.state.harness_orchestrator = HarnessOrchestrator()
        logger.info(
            "lifespan.harness.initialized",
            handlers=app.state.harness_orchestrator.handler_names,
        )
    except Exception as exc:
        logger.warning("lifespan.harness.failed", detail=str(exc))

    # ── Warmup: business resources ──────────────────────────────────────
    # Pre-load heavy models to avoid cold-start latency on first request.
    # Failures are non-critical — the resources will lazy-load on first use.

    try:
        from retrieval.embedders.embedding_model import EmbeddingModel

        model = EmbeddingModel.get_instance()
        _ = model.dimension  # triggers _ensure_loaded(), loads PyTorch model
        logger.info("lifespan.embedding.warmed_up", dim=model.dimension)
    except Exception as exc:
        logger.warning("lifespan.embedding.warmup_failed", detail=str(exc))

    try:
        from models.prompts.prompt_manager import get_prompt_manager

        get_prompt_manager()  # pre-loads all .jinja2 templates
        logger.info("lifespan.prompts.warmed_up")
    except Exception as exc:
        logger.warning("lifespan.prompts.warmup_failed", detail=str(exc))

    # ── MCP Servers (background sub‑processes) ──────────────────────────
    import uvicorn

    mcp_tasks: list[asyncio.Task] = []

    try:
        from mcp_tools.mcp_servers.search_server import app as search_app

        search_config = uvicorn.Config(search_app, host="0.0.0.0", port=8001, log_level="info")
        search_server = uvicorn.Server(search_config)
        mcp_tasks.append(asyncio.create_task(search_server.serve(), name="mcp-search"))
        logger.info("lifespan.mcp_search.starting", port=8001)
    except Exception as exc:
        logger.warning("lifespan.mcp_search.failed", detail=str(exc))

    try:
        from mcp_tools.mcp_servers.chart_server import app as chart_app

        chart_config = uvicorn.Config(chart_app, host="0.0.0.0", port=8003, log_level="info")
        chart_server = uvicorn.Server(chart_config)
        mcp_tasks.append(asyncio.create_task(chart_server.serve(), name="mcp-chart"))
        logger.info("lifespan.mcp_chart.starting", port=8003)
    except Exception as exc:
        logger.warning("lifespan.mcp_chart.failed", detail=str(exc))

    app.state.mcp_tasks = mcp_tasks

    logger.info("lifespan.ready")
    # Checkpointer lifecycle — keep connection pool alive for app lifetime
    async with create_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer
        yield
        # checkpointer context exit → connection pool closed
    # ── Shutdown MCP servers ───────────────────────────────────────────
    mcp_tasks: list[asyncio.Task] = getattr(app.state, "mcp_tasks", [])
    for t in mcp_tasks:
        t.cancel()
    for t in mcp_tasks:
        try:
            await t
        except asyncio.CancelledError:
            logger.info("lifespan.mcp_server.cancelled", name=task.get_name())
    shutdown_tracer()
    logger.info("app.stopped")


def _handle_startup_error(service: str, exc: Exception) -> None:
    if settings.environment == "prod":
        logger.critical("lifespan.service_failed", service=service, exc_info=True)
    else:
        logger.warning("lifespan.service_unavailable", service=service, detail=str(exc))


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
app.add_middleware(AuthMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window,
)

# ── Routers ───────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(index.router)
app.include_router(task.router)
app.include_router(session_router)


# ── Main entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=settings.host, port=settings.port, reload=settings.debug)
