"""Per-tenant Qdrant collection naming and lifecycle utilities.

Collection naming convention::

    {tenant_id}_{base_collection}

When no tenant is active, the base collection name is used unchanged.
All functions are async and use the shared Qdrant client from
``infrastructure.vector_db.qdrant_client``.

AGENTS.md §6.1 compliant: uses strategy pattern through ``TenantContext``
rather than hard-coded branches.
"""

from __future__ import annotations

import logging

from infrastructure.vector_db.qdrant_client import collection_exists, ensure_collection

logger = logging.getLogger(__name__)


# ── Collection name helpers ───────────────────────────────────────────────


def make_tenant_collection_name(
    tenant_id: str | None,
    base_name: str,
) -> str:
    """Build a tenant-scoped Qdrant collection name.

    Args:
        tenant_id: Tenant identifier. ``None`` or ``"default"`` uses
            ``base_name`` unchanged.
        base_name: Base collection name (e.g. ``"documents"``).

    Returns:
        Scoped name ``"{tenant_id}_{base_name}"`` or just ``base_name``
        for the default tenant.

    Examples:
        >>> make_tenant_collection_name("acme", "documents")
        'acme_documents'
        >>> make_tenant_collection_name(None, "documents")
        'documents'
        >>> make_tenant_collection_name("default", "documents")
        'documents'
    """
    if not tenant_id or tenant_id == "default":
        return base_name
    return f"{tenant_id}_{base_name}"


def make_tenant_collection_name_from_ctx(
    base_name: str,
) -> str:
    """Build a tenant-scoped collection name using the current tenant context.

    Convenience wrapper around ``make_tenant_collection_name`` that reads
    ``tenant_id`` from ``get_current_tenant()``.

    Args:
        base_name: Base collection name.

    Returns:
        Scoped collection name.
    """
    from infrastructure.multi_tenant.tenant_context import get_current_tenant

    ctx = get_current_tenant()
    return make_tenant_collection_name(ctx.tenant_id, base_name)


# ── Collection lifecycle ─────────────────────────────────────────────────


async def ensure_tenant_collection(
    tenant_id: str | None,
    base_name: str,
    vector_size: int = 1024,
) -> str:
    """Ensure a tenant-scoped Qdrant collection exists, creating it if needed.

    Args:
        tenant_id: Tenant identifier.
        base_name: Base collection name.
        vector_size: Embedding vector dimensionality (default 1024 for bge-m3).

    Returns:
        The tenant-scoped collection name that is guaranteed to exist.
    """
    name = make_tenant_collection_name(tenant_id, base_name)
    await ensure_collection(name, vector_size=vector_size)
    logger.info(
        "qdrant_tenant.collection_ensured",
        tenant_id=tenant_id or "default",
        collection=name,
    )
    return name


async def ensure_tenant_collection_from_ctx(
    base_name: str,
    vector_size: int = 1024,
) -> str:
    """Ensure a tenant-scoped collection exists using the current tenant context.

    Args:
        base_name: Base collection name.
        vector_size: Embedding vector dimensionality.

    Returns:
        The tenant-scoped collection name that is guaranteed to exist.
    """
    from infrastructure.multi_tenant.tenant_context import get_current_tenant

    ctx = get_current_tenant()
    return await ensure_tenant_collection(ctx.tenant_id, base_name, vector_size)


async def tenant_collection_exists(
    tenant_id: str | None,
    base_name: str,
) -> bool:
    """Check whether a tenant-scoped collection exists.

    Args:
        tenant_id: Tenant identifier.
        base_name: Base collection name.

    Returns:
        ``True`` if the collection exists.
    """
    name = make_tenant_collection_name(tenant_id, base_name)
    return await collection_exists(name)
