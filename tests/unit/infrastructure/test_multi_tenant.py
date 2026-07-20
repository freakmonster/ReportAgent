"""Tests for multi-tenant isolation infrastructure.

Covers:
- TenantContext creates correct collection names
- user_id extraction from context
- Rate limit differentiation per tenant
- Qdrant collection prefix handling
"""

from __future__ import annotations

import pytest

from infrastructure.multi_tenant.qdrant_tenant import (
    make_tenant_collection_name,
    make_tenant_collection_name_from_ctx,
    tenant_collection_exists,
)
from infrastructure.multi_tenant.rate_limiter import (
    TenantRateQuota,
    build_rate_limit_key,
    get_tenant_quota,
)
from infrastructure.multi_tenant.tenant_context import (
    DEFAULT_TENANT_ID,
    TenantContext,
    get_current_tenant,
    reset_current_tenant,
    set_current_tenant,
    tenant_scope,
)

# ═══════════════════════════════════════════════════════════════════════════
# TenantContext — collection names
# ═══════════════════════════════════════════════════════════════════════════


class TestTenantContextCollectionNames:
    """TenantContext creates correct collection names."""

    def test_default_context_collection_prefix(self):
        """Default context uses empty prefix (consistent with make_tenant_collection_name)."""
        ctx = TenantContext()
        assert ctx.collection_prefix == ""

    def test_custom_tenant_collection_prefix(self):
        """Custom tenant_id becomes the prefix."""
        ctx = TenantContext(tenant_id="acme")
        assert ctx.collection_prefix == "acme_"

    def test_explicit_qdrant_prefix_overrides_tenant_id(self):
        """Explicit qdrant_collection_prefix takes priority over tenant_id."""
        ctx = TenantContext(
            tenant_id="acme",
            qdrant_collection_prefix="tenant_acme",
        )
        assert ctx.collection_prefix == "tenant_acme_"

    def test_empty_qdrant_prefix_falls_back_to_tenant_id(self):
        """Empty qdrant_collection_prefix falls back to tenant_id prefix."""
        ctx = TenantContext(
            tenant_id="acme",
            qdrant_collection_prefix="",
        )
        assert ctx.collection_prefix == "acme_"


# ═══════════════════════════════════════════════════════════════════════════
# TenantContext — user_id
# ═══════════════════════════════════════════════════════════════════════════


class TestTenantContextUserId:
    """user_id extraction from context."""

    def test_default_user_id(self):
        """Default user_id is 'anonymous'."""
        ctx = TenantContext()
        assert ctx.user_id == "anonymous"

    def test_explicit_user_id(self):
        """Explicit user_id is preserved."""
        ctx = TenantContext(tenant_id="acme", user_id="user-42")
        assert ctx.user_id == "user-42"

    def test_rate_limit_quota_default(self):
        """rate_limit_quota defaults to None."""
        ctx = TenantContext()
        assert ctx.rate_limit_quota is None

    def test_rate_limit_quota_override(self):
        """rate_limit_quota can be overridden per tenant."""
        ctx = TenantContext(tenant_id="acme", rate_limit_quota=200)
        assert ctx.rate_limit_quota == 200


# ═══════════════════════════════════════════════════════════════════════════
# Context manager — tenant_scope
# ═══════════════════════════════════════════════════════════════════════════


class TestTenantScope:
    """Async context manager activates tenant correctly."""

    @pytest.mark.asyncio
    async def test_scope_sets_context(self):
        """Inside the scope, get_current_tenant returns the active tenant."""
        reset_current_tenant()
        async with tenant_scope("acme", user_id="u-1") as ctx:
            current = get_current_tenant()
            assert current.tenant_id == "acme"
            assert current.user_id == "u-1"
            assert ctx.tenant_id == "acme"

    @pytest.mark.asyncio
    async def test_scope_restores_previous(self):
        """After scope exit, previous context is restored."""
        reset_current_tenant()
        prev = TenantContext(tenant_id="before")
        set_current_tenant(prev)

        async with tenant_scope("acme") as ctx:
            assert ctx.tenant_id == "acme"

        restored = get_current_tenant()
        assert restored.tenant_id == "before"

    @pytest.mark.asyncio
    async def test_scope_restores_none_to_default(self):
        """After scope exit with None prior, get_current_tenant returns default."""
        reset_current_tenant()
        async with tenant_scope("acme"):
            pass
        current = get_current_tenant()
        assert current.tenant_id == DEFAULT_TENANT_ID


# ═══════════════════════════════════════════════════════════════════════════
# Qdrant — collection naming
# ═══════════════════════════════════════════════════════════════════════════


class TestQdrantCollectionNaming:
    """Qdrant collection prefix handling."""

    def test_default_tenant_returns_base_name(self):
        """Default tenant uses base_name unchanged."""
        assert make_tenant_collection_name("default", "documents") == "documents"

    def test_none_tenant_returns_base_name(self):
        """None tenant_id uses base_name unchanged."""
        assert make_tenant_collection_name(None, "documents") == "documents"

    def test_empty_tenant_returns_base_name(self):
        """Empty string tenant_id uses base_name unchanged."""
        assert make_tenant_collection_name("", "documents") == "documents"

    def test_custom_tenant_prefixes_collection(self):
        """Custom tenant_id is prefixed."""
        assert make_tenant_collection_name("acme", "documents") == "acme_documents"

    def test_tenant_with_special_chars(self):
        """Tenant IDs with hyphens/underscores work."""
        assert make_tenant_collection_name("org-42", "reports") == "org-42_reports"

    def test_nested_base_name(self):
        """Base name with underscores works."""
        assert (
            make_tenant_collection_name("acme", "research_reports_index")
            == "acme_research_reports_index"
        )

    @pytest.mark.asyncio
    async def test_collection_exists_uses_tenant_name(self, monkeypatch):
        """tenant_collection_exists delegates to collection_exists with tenant name."""
        called_with: list[str] = []

        async def fake_exists(name: str) -> bool:
            called_with.append(name)
            return True

        monkeypatch.setattr(
            "infrastructure.multi_tenant.qdrant_tenant.collection_exists",
            fake_exists,
        )

        result = await tenant_collection_exists("acme", "docs")
        assert result is True
        assert called_with == ["acme_docs"]

    @pytest.mark.asyncio
    async def test_collection_exists_default_tenant(self, monkeypatch):
        """Default tenant uses bare collection name."""
        called_with: list[str] = []

        async def fake_exists(name: str) -> bool:
            called_with.append(name)
            return True

        monkeypatch.setattr(
            "infrastructure.multi_tenant.qdrant_tenant.collection_exists",
            fake_exists,
        )

        result = await tenant_collection_exists("default", "docs")
        assert result is True
        assert called_with == ["docs"]

    @pytest.mark.asyncio
    async def test_collection_name_from_ctx(self):
        """make_tenant_collection_name_from_ctx reads from current context."""
        reset_current_tenant()
        set_current_tenant(TenantContext(tenant_id="acme"))
        assert make_tenant_collection_name_from_ctx("reports") == "acme_reports"


# ═══════════════════════════════════════════════════════════════════════════
# Rate limiter — per-tenant differentiation
# ═══════════════════════════════════════════════════════════════════════════


class TestRateLimitKey:
    """Rate limit key differentiation per tenant."""

    def test_default_tenant_key(self):
        """Default tenant uses global key."""
        assert build_rate_limit_key("u-1") == "ratelimit:u-1"
        assert build_rate_limit_key("u-1", "default") == "ratelimit:u-1"

    def test_tenant_key_includes_tenant_id(self):
        """Per-tenant key includes tenant_id namespace."""
        assert build_rate_limit_key("u-1", "acme") == "ratelimit:acme:u-1"

    def test_different_tenants_have_different_keys(self):
        """Two tenants share same user_id but have distinct keys."""
        key_a = build_rate_limit_key("u-1", "acme")
        key_b = build_rate_limit_key("u-1", "beta")
        assert key_a != key_b

    def test_same_tenant_different_users_have_different_keys(self):
        """Same tenant, different users → different keys."""
        key_a = build_rate_limit_key("u-1", "acme")
        key_b = build_rate_limit_key("u-2", "acme")
        assert key_a != key_b

    def test_none_tenant_defaults_to_global(self):
        """None tenant_id produces global key."""
        assert build_rate_limit_key("u-1", None) == "ratelimit:u-1"


class TestTenantRateQuota:
    """Per-tenant rate quotas."""

    def test_default_quota(self):
        """Default quota uses 60/60."""
        q = TenantRateQuota()
        assert q.max_requests == 60
        assert q.window_seconds == 60

    def test_custom_quota(self):
        """Custom quota values."""
        q = TenantRateQuota(max_requests=100, window_seconds=30)
        assert q.max_requests == 100
        assert q.window_seconds == 30

    def test_get_tenant_quota_default(self):
        """get_tenant_quota returns global default for 'default' tenant."""
        quota = get_tenant_quota("default")
        assert isinstance(quota, TenantRateQuota)
        assert quota.max_requests > 0
        assert quota.window_seconds > 0

    def test_get_tenant_quota_none(self):
        """get_tenant_quota returns global default for None."""
        quota = get_tenant_quota(None)
        assert isinstance(quota, TenantRateQuota)
        assert quota.max_requests > 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration — context isolation
# ═══════════════════════════════════════════════════════════════════════════


class TestTenantIsolationIntegration:
    """End-to-end isolation: context → collection name → rate limit key."""

    @pytest.mark.asyncio
    async def test_full_tenant_isolation_flow(self):
        """A tenant gets isolated collection names and rate limit keys."""
        reset_current_tenant()

        async with tenant_scope("acme", user_id="u-42") as ctx:
            # Collection naming
            col_name = make_tenant_collection_name(ctx.tenant_id, "reports")
            assert col_name == "acme_reports"

            # Rate limit key
            rl_key = build_rate_limit_key(ctx.user_id, ctx.tenant_id)
            assert rl_key == "ratelimit:acme:u-42"

            # Collection prefix
            assert ctx.collection_prefix == "acme_"

    @pytest.mark.asyncio
    async def test_different_tenants_stay_isolated(self):
        """Two concurrent tenants must not leak into each other."""
        reset_current_tenant()

        async with tenant_scope("acme", user_id="u-1") as ctx_a:
            col_a = make_tenant_collection_name(ctx_a.tenant_id, "data")
            rl_a = build_rate_limit_key(ctx_a.user_id, ctx_a.tenant_id)

            async with tenant_scope("beta", user_id="u-2"):
                col_b = make_tenant_collection_name_from_ctx("data")

            # After inner scope exits, outer context must be restored
            current = get_current_tenant()
            assert current.tenant_id == "acme"
            assert current.user_id == "u-1"

            assert col_a == "acme_data"
            assert col_b == "beta_data"
            assert rl_a == "ratelimit:acme:u-1"
            assert col_a != col_b
