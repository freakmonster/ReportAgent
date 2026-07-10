"""FastAPI application entry point for the 智能研报生成系统.

Provides a minimal skeleton with health-check endpoint and CORS middleware,
ready for phased expansion with LangGraph agent workflows.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from structlog import get_logger

from config.settings import settings

# ── Structured logging ────────────────────────────────────────────────

logger = get_logger(__name__)


# ── Lifespan events ───────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    logger.info(
        "app.starting",
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
        host=settings.host,
        port=settings.port,
    )
    yield
    logger.info("app.stopped")


# ── FastAPI application ───────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS — allow all origins during initial development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return a simple health-check response.

    Returns:
        dict with status "ok" when the service is running.
    """
    return {"status": "ok"}


# ── Main entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO)
    )
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
