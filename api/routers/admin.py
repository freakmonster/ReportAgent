"""Admin router — runtime feature flag management, system status, and dashboard.

Endpoints:
- GET  /admin/flags              — list all feature flags with current states
- GET  /admin/flags/{name}       — get a single flag
- PUT  /admin/flags/{name}       — toggle a flag (hot-switch, no restart)
- DELETE /admin/flags/{name}     — reset a flag to YAML default
- GET  /admin/status             — system health overview
- GET  /admin/dashboard/overview — usage overview aggregation
- GET  /admin/dashboard/recent   — recent workflow activity
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.admin import (
    AdminStatusResponse,
    FeatureFlagItem,
    FeatureFlagResetResponse,
    FeatureFlagsResponse,
    FeatureFlagUpdateRequest,
    FeatureFlagUpdateResponse,
)
from config.feature_flags import get_flag_manager
from config.settings import settings

router = APIRouter(prefix="/admin", tags=["admin"])

# ── Feature Flags ──────────────────────────────────────────────────────────


@router.get("/flags", response_model=FeatureFlagsResponse)
async def list_flags() -> FeatureFlagsResponse:
    """List all feature flags with their current effective values and sources."""
    mgr = get_flag_manager()
    effective = await mgr.get_all()

    items: dict[str, FeatureFlagItem] = {}
    for name, value in effective.items():
        # Determine source: if Redis has an override, it's 'redis'
        source = "redis" if await _has_redis_override(name) else "default"
        items[name] = FeatureFlagItem(name=name, enabled=value, source=source)

    return FeatureFlagsResponse(flags=items, total=len(items))


@router.get("/flags/{name}", response_model=FeatureFlagItem)
async def get_flag(name: str) -> FeatureFlagItem:
    """Get a single feature flag's current state."""
    mgr = get_flag_manager()
    try:
        value = await mgr.get(name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Flag '{name}' not found")

    source = "redis" if await _has_redis_override(name) else "default"
    return FeatureFlagItem(name=name, enabled=value, source=source)


@router.put("/flags/{name}", response_model=FeatureFlagUpdateResponse)
async def update_flag(name: str, body: FeatureFlagUpdateRequest) -> FeatureFlagUpdateResponse:
    """Toggle a feature flag at runtime. No restart required.

    The new value is persisted in Redis and takes effect immediately
    across all worker processes.
    """
    mgr = get_flag_manager()
    try:
        await mgr.set(name, body.enabled)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Flag '{name}' not found")

    return FeatureFlagUpdateResponse(
        name=name,
        enabled=body.enabled,
        message=f"Flag '{name}' set to {body.enabled}",
    )


@router.delete("/flags/{name}", response_model=FeatureFlagResetResponse)
async def reset_flag(name: str) -> FeatureFlagResetResponse:
    """Reset a feature flag to its YAML default value."""
    mgr = get_flag_manager()
    try:
        await mgr.reset(name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Flag '{name}' not found")

    default = await mgr.get(name)
    return FeatureFlagResetResponse(
        name=name,
        message=f"Flag '{name}' reset to default",
        reset_to=default,
    )


# ── System Status ──────────────────────────────────────────────────────────


@router.get("/status", response_model=AdminStatusResponse)
async def system_status() -> AdminStatusResponse:
    """Return system overview: version, environment, feature flags, services."""
    mgr = get_flag_manager()

    services: dict[str, str] = {}
    # Quick health probes
    try:
        from infrastructure.database.connection import engine

        services["postgresql"] = "connected" if engine else "unknown"
    except Exception:
        services["postgresql"] = "unavailable"

    try:
        from infrastructure.cache.redis_client import get_redis

        await get_redis().ping()
        services["redis"] = "connected"
    except Exception:
        services["redis"] = "unavailable"

    try:
        from infrastructure.vector_db.qdrant_client import get_qdrant

        await get_qdrant().get_collections()
        services["qdrant"] = "connected"
    except Exception:
        services["qdrant"] = "unavailable"

    return AdminStatusResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
        feature_flags=await mgr.get_all(),
        services=services,
    )


# ── Dashboard ───────────────────────────────────────────────────────────────


@router.get("/dashboard/overview")
async def dashboard_overview(days: int = 7) -> dict:
    """Return usage overview: total requests, success rate, tokens, avg duration, by-template breakdown."""
    from infrastructure.database.repositories.usage_repo import get_usage_repo

    repo = get_usage_repo()
    return await repo.get_overview(days)


@router.get("/dashboard/recent")
async def dashboard_recent(limit: int = 20) -> list[dict]:
    """Return the most recent workflow entries."""
    from infrastructure.database.repositories.usage_repo import get_usage_repo

    repo = get_usage_repo()
    return await repo.get_recent(limit)


# ── Helpers ────────────────────────────────────────────────────────────────


async def _has_redis_override(name: str) -> bool:
    """Check if a flag has a Redis override set."""
    try:
        from config.feature_flags import FeatureFlagManager
        from infrastructure.cache.redis_client import get_redis

        redis = get_redis()
        val = await redis.get(FeatureFlagManager._key(name))
        return val is not None
    except Exception:
        return False
