"""Multi-tenant isolation infrastructure.

Exports the core building blocks for tenant-aware operations:

- ``TenantContext``: immutable tenant scope with isolation identifiers.
- ``tenant_scope``: async context manager activating a tenant for a coroutine.
- ``get_current_tenant`` / ``set_current_tenant``: contextvar accessors.
- ``make_tenant_collection_name`` / ``ensure_tenant_collection``: per-tenant
  Qdrant collection naming and lifecycle.
- ``TenantRateLimitMiddleware``: tenant-aware sliding-window rate limiter.
- ``build_rate_limit_key`` / ``get_tenant_quota``: rate-limit utilities.
"""

from __future__ import annotations

from infrastructure.multi_tenant.qdrant_tenant import (
    ensure_tenant_collection,
    ensure_tenant_collection_from_ctx,
    make_tenant_collection_name,
    make_tenant_collection_name_from_ctx,
    tenant_collection_exists,
)
from infrastructure.multi_tenant.rate_limiter import (
    TenantRateLimitMiddleware,
    TenantRateQuota,
    build_rate_limit_key,
    get_tenant_quota,
    get_tenant_quota_from_ctx,
)
from infrastructure.multi_tenant.tenant_context import (
    DEFAULT_TENANT_ID,
    TenantContext,
    get_current_tenant,
    reset_current_tenant,
    set_current_tenant,
    tenant_scope,
)

__all__ = [
    # Tenant context
    "TenantContext",
    "DEFAULT_TENANT_ID",
    "get_current_tenant",
    "set_current_tenant",
    "reset_current_tenant",
    "tenant_scope",
    # Qdrant tenant helpers
    "make_tenant_collection_name",
    "make_tenant_collection_name_from_ctx",
    "ensure_tenant_collection",
    "ensure_tenant_collection_from_ctx",
    "tenant_collection_exists",
    # Rate limiter
    "TenantRateLimitMiddleware",
    "TenantRateQuota",
    "build_rate_limit_key",
    "get_tenant_quota",
    "get_tenant_quota_from_ctx",
]
