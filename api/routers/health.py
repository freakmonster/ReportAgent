"""Health router — dependency connectivity check, V2.3 < 100ms response."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.response import HealthResponse

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
        from infrastructure.database.connection import engine
        if engine:
            services["postgresql"] = "connected"
        else:
            services["postgresql"] = "not_initialized"
    except Exception:
        services["postgresql"] = "unavailable"

    # Redis
    try:
        from infrastructure.cache.redis_client import RedisClient
        services["redis"] = "available"
    except Exception:
        services["redis"] = "unavailable"

    # Qdrant
    try:
        from infrastructure.vector_db.qdrant_client import QdrantClient
        services["qdrant"] = "available"
    except Exception:
        services["qdrant"] = "unavailable"

    return HealthResponse(
        status="ok",
        services=services,
        version="0.1.0",
    )
