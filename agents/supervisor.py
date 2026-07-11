"""Supervisor — task dispatch with Redis distributed lock.

Prevents concurrent execution of the same workflow.
"""

from __future__ import annotations

from typing import Any


async def acquire_workflow_lock(
    workflow_id: str,
    redis_client: object | None = None,
    ttl: int = 3600,
) -> bool:
    """Acquire a distributed lock for a workflow.

    Uses Redis SETNX with TTL to prevent concurrent runs of the same workflow.

    Args:
        workflow_id: Unique workflow identifier.
        redis_client: Redis async client (optional; uses lazy import if None).
        ttl: Lock TTL in seconds.

    Returns:
        True if lock was acquired, False if another instance is running.
    """
    if redis_client is None:
        try:
            from infrastructure.cache.redis_client import RedisClient
            redis_client = RedisClient()
        except ImportError:
            # Redis not available — allow execution (dev mode)
            return True

    try:
        key = f"lock:workflow:{workflow_id}"
        # SETNX equivalent: set key only if it doesn't exist
        acquired = await redis_client.set(key, "1", ex=ttl, nx=True)  # type: ignore[union-attr]
        return bool(acquired)
    except Exception:
        # If Redis is unreachable, allow execution
        return True


async def release_workflow_lock(
    workflow_id: str,
    redis_client: object | None = None,
) -> None:
    """Release the distributed lock for a workflow."""
    if redis_client is None:
        return
    try:
        key = f"lock:workflow:{workflow_id}"
        await redis_client.delete(key)  # type: ignore[union-attr]
    except Exception:
        pass
