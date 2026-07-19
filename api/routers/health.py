"""Health router — dependency connectivity check, V2.3 < 100ms response."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from api.schemas.response import HealthResponse
from infrastructure.observability.metrics import get_metrics

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check connectivity to all dependent services.

    V2.3 requirement: < 100ms response time.
    Only checks critical infrastructure (PG/Redis/Qdrant), not lazy business resources.
    """
    services: dict[str, str] = {}

    # PostgreSQL
    try:
        from sqlalchemy import text
        from infrastructure.database.connection import get_db
        async with get_db() as session:
            await session.execute(text("SELECT 1"))
        services["postgresql"] = "connected"
    except Exception:
        services["postgresql"] = "unavailable"

    # Redis
    try:
        from infrastructure.cache.redis_client import get_redis
        await get_redis().ping()
        services["redis"] = "connected"
    except Exception as exc:
        if "HELLO" in str(exc):
            # Redis 5.x — RESP3 unavailable but basic commands work
            services["redis"] = "degraded (Redis < 6.0, RESP3 unavailable)"
        else:
            services["redis"] = "unavailable"

    # Qdrant
    try:
        from infrastructure.vector_db.qdrant_client import get_qdrant
        await get_qdrant().get_collections()
        services["qdrant"] = "connected"
    except Exception:
        services["qdrant"] = "unavailable"

    return HealthResponse(
        status="ok",
        services=services,
        version="0.1.0",
    )


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns text-format metrics for Prometheus scraping.
    Requires authentication (via AuthMiddleware).
    """
    return Response(content=get_metrics(), media_type="text/plain")
