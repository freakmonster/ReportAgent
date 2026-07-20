"""Tenant isolation context — dataclass and context manager.

Provides the canonical ``TenantContext`` that flows through the workflow
state via ``ReportState["base"]["tenant_id"]`` and is made available
globally via ``contextvars`` for cross-cutting concerns (rate limiting,
Qdrant collection naming, logging).

AGENTS.md §1.3 compliant: tenant_id lives in BaseContext, not a flat
monolithic State dict.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# ── Context variable: carries TenantContext through async call chains ──
_current_tenant: contextvars.ContextVar["TenantContext | None"] = contextvars.ContextVar(
    "current_tenant", default=None
)

# Default tenant ID used when no tenant context is active
DEFAULT_TENANT_ID = "default"
DEFAULT_QDRANT_PREFIX = ""


@dataclass(slots=True)
class TenantContext:
    """Immutable tenant context carrying isolation identifiers.

    Attributes:
        tenant_id: Unique tenant identifier.
        user_id: Authenticated user within this tenant.
        qdrant_collection_prefix: Prefix applied to Qdrant collections for
            this tenant (e.g. ``"t_acme"`` → collections named
            ``t_acme_documents``).
        rate_limit_quota: Override for per-tenant rate limit.
    """

    tenant_id: str = DEFAULT_TENANT_ID
    user_id: str = "anonymous"
    qdrant_collection_prefix: str = DEFAULT_QDRANT_PREFIX
    rate_limit_quota: int | None = None

    @property
    def collection_prefix(self) -> str:
        """Effective Qdrant collection prefix for this tenant.

        Returns a trailing-underscore prefix (e.g. ``"acme_"``) that can be
        concatenated with a base collection name. Returns ``""`` for the
        default tenant so that naming is consistent with
        ``make_tenant_collection_name``.
        """
        if self.tenant_id == DEFAULT_TENANT_ID:
            return ""
        if self.qdrant_collection_prefix:
            return f"{self.qdrant_collection_prefix}_"
        return f"{self.tenant_id}_"


# ── Global helpers ───────────────────────────────────────────────────────


def get_current_tenant() -> TenantContext:
    """Return the current tenant context or a default fallback.

    Never returns None — guarantees safe usage in code paths that
    may execute outside a ``tenant_scope()`` block.
    """
    ctx = _current_tenant.get()
    if ctx is None:
        return TenantContext()  # "default" tenant
    return ctx


def set_current_tenant(ctx: TenantContext) -> None:
    """Set the current tenant context on the context variable."""
    _current_tenant.set(ctx)


def reset_current_tenant() -> None:
    """Reset the tenant context variable to its default (None)."""
    _current_tenant.set(None)


# ── Context manager ──────────────────────────────────────────────────────


@asynccontextmanager
async def tenant_scope(
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = "anonymous",
    qdrant_collection_prefix: str = DEFAULT_QDRANT_PREFIX,
    rate_limit_quota: int | None = None,
) -> AsyncIterator[TenantContext]:
    """Async context manager that activates a tenant for the calling coroutine.

    Usage::

        async with tenant_scope("acme", user_id="u-42") as ctx:
            collection_name = f"{ctx.collection_prefix}documents"
            # All nested calls see the same tenant via get_current_tenant()

    The tenant context is restored to its previous value on exit.

    Args:
        tenant_id: Tenant identifier.
        user_id: User within the tenant.
        qdrant_collection_prefix: Optional override for Qdrant prefix.
        rate_limit_quota: Per-tenant rate limit override.

    Yields:
        Active TenantContext instance.
    """
    prev = _current_tenant.get()
    ctx = TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        qdrant_collection_prefix=qdrant_collection_prefix,
        rate_limit_quota=rate_limit_quota,
    )
    _current_tenant.set(ctx)
    logger.debug(
        "tenant_scope.enter",
        tenant_id=tenant_id,
        user_id=user_id,
    )
    try:
        yield ctx
    finally:
        _current_tenant.set(prev)
        logger.debug("tenant_scope.exit", tenant_id=tenant_id)
