"""Per-tenant enhanced rate limiter with configurable per-tenant quotas.

Extends the existing ``RateLimitMiddleware`` pattern with tenant-aware
isolation. Rate limit keys follow the convention::

    ratelimit:{tenant_id}:{user_id}

Per-tenant quotas are loaded from YAML configuration (``rate_limit.tenants``
block). When no tenant-specific quota is configured, the global default
applies.

AGENTS.md §6.1 compliant: strategy pattern through per-tenant quota
lookup rather than hard-coded tenant branches. §6.2 compliant: quotas
controlled by YAML config.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


# ── Rate limit key builder ──────────────────────────────────────────────


def build_rate_limit_key(user_id: str, tenant_id: str | None = None) -> str:
    """Construct a tenant-scoped rate-limit Redis key.

    Args:
        user_id: Authenticated user ID.
        tenant_id: Tenant identifier. ``None`` or ``"default"`` uses the
            global key ``ratelimit:{user_id}``.

    Returns:
        Namespaced key string.
    """
    if not tenant_id or tenant_id == "default":
        return f"ratelimit:{user_id}"
    return f"ratelimit:{tenant_id}:{user_id}"


# ── Quota lookup ────────────────────────────────────────────────────────


@dataclass(slots=True)
class TenantRateQuota:
    """Per-tenant rate limit configuration."""

    max_requests: int = 60
    window_seconds: int = 60


# Module-level tenant quota registry initialised from YAML config
_tenant_quotas: dict[str, TenantRateQuota] = {}


def _load_tenant_quotas_from_yaml() -> dict[str, TenantRateQuota]:
    """Load per-tenant rate quotas from YAML configuration.

    Reads the active environment YAML file directly to extract the
    ``rate_limit.tenants`` block.  This avoids coupling to the Pydantic
    Settings model (which drops unknown keys via ``extra="ignore"``).

    Returns:
        Dict of tenant_id → TenantRateQuota.
    """
    import os
    import yaml
    from pathlib import Path

    try:
        env = os.getenv("ENVIRONMENT", "dev")
        config_dir = Path(__file__).resolve().parents[3] / "config" / "environments"
        yaml_path = config_dir / f"{env}.yaml"

        if not yaml_path.exists():
            yaml_path = config_dir / "dev.yaml"
        if not yaml_path.exists():
            return {}

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        rate_limit_block = data.get("rate_limit", {})
        if isinstance(rate_limit_block, dict):
            tenants = rate_limit_block.get("tenants", {}) if isinstance(rate_limit_block, dict) else {}
        else:
            tenants = {}

        if tenants:
            return {
                str(tid): TenantRateQuota(
                    max_requests=int(t.get("max_requests", 60)),
                    window_seconds=int(t.get("window_seconds", 60)),
                )
                for tid, t in tenants.items()
            }
    except Exception:
        pass
    return {}


def get_tenant_quota(tenant_id: str | None) -> TenantRateQuota:
    """Return the rate quota for a specific tenant.

    Falls back to the global default when no per-tenant quota is configured.

    Args:
        tenant_id: Tenant identifier.

    Returns:
        TenantRateQuota instance (never None).
    """
    global _tenant_quotas
    if not _tenant_quotas:
        _tenant_quotas = _load_tenant_quotas_from_yaml()

    if tenant_id and tenant_id != "default" and tenant_id in _tenant_quotas:
        return _tenant_quotas[tenant_id]

    from config.settings import settings

    return TenantRateQuota(
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window,
    )


def get_tenant_quota_from_ctx() -> TenantRateQuota:
    """Return the rate quota using the current tenant context."""
    from infrastructure.multi_tenant.tenant_context import get_current_tenant

    ctx = get_current_tenant()
    if ctx.rate_limit_quota is not None:
        return TenantRateQuota(
            max_requests=ctx.rate_limit_quota,
            window_seconds=60,
        )
    return get_tenant_quota(ctx.tenant_id)


# ── Tenant-aware rate limit middleware ──────────────────────────────────


class TenantRateLimitMiddleware:
    """Tenant-aware sliding-window rate limiter.

    Extends the ``RateLimitMiddleware`` pattern with per-tenant isolation.
    Each (tenant_id, user_id) pair gets an independent rate-limit window.

    Primary backend: Redis ZSET.
    Fallback backend: in-memory dict.
    """

    def __init__(
        self,
        app,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        self.app = app
        self._max_requests = max_requests
        self._window = window_seconds
        self._fallback_counters: dict[str, list[float]] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        user_id = getattr(request.state, "user_id", "anonymous")
        tenant_id = getattr(request.state, "tenant_id", "default")

        # Resolve per-tenant quota
        quota = get_tenant_quota(tenant_id)
        max_req = quota.max_requests
        window = quota.window_seconds

        key = build_rate_limit_key(user_id, tenant_id)

        # ── Redis path ──────────────────────────────────────────────
        try:
            from infrastructure.cache.redis_client import get_redis

            redis = get_redis()
            now = time.time()
            window_start = now - window

            pipe = redis.pipeline(transaction=True)
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            results = await pipe.execute()
            count = results[1]

            if count >= max_req:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                )
                await response(scope, receive, send)
                return

            await redis.zadd(key, {str(now): now})
            await redis.expire(key, int(window) + 1)

        except Exception:
            # Redis unavailable → fall back to in-memory
            await self._fallback_check(scope, receive, send, key, max_req, window)
            return

        await self.app(scope, receive, send)

    async def _fallback_check(
        self,
        scope,
        receive,
        send,
        key: str,
        max_req: int,
        window: int,
    ) -> None:
        """In-memory sliding window fallback."""
        now = time.time()
        if key not in self._fallback_counters:
            self._fallback_counters[key] = []
        self._fallback_counters[key] = [
            t for t in self._fallback_counters[key]
            if now - t < window
        ]
        if len(self._fallback_counters[key]) >= max_req:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
            await response(scope, receive, send)
            return
        self._fallback_counters[key].append(now)
        await self.app(scope, receive, send)
