"""Redis async client wrapper with connection pool and distributed locking."""

from typing import Optional

import redis.asyncio as aioredis

from config.settings import settings

# ── Module-level client ─────────────────────────────────────
_redis_client: aioredis.Redis | None = None


async def init_redis() -> None:
    """Initialise the Redis async client with a connection pool (idempotent)."""
    global _redis_client

    if _redis_client is not None:
        return

    _redis_client = aioredis.Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_client

    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


def get_redis() -> aioredis.Redis:
    """Return the shared Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialised. Call init_redis() before get_redis().")
    return _redis_client


# ── Helper methods ──────────────────────────────────────────


async def set_with_ttl(key: str, value: str, ttl: int) -> None:
    """Set a key with a time-to-live (seconds)."""
    client = get_redis()
    await client.set(key, value, ex=ttl)


async def get_and_delete(key: str) -> Optional[str]:
    """Atomically get the value of a key and then delete it."""
    client = get_redis()
    async with client.pipeline(transaction=True) as pipe:
        value = await pipe.get(key).delete(key).execute()
    return value[0] if value else None


async def acquire_lock(key: str, ttl: int = 30) -> bool:
    """Acquire a distributed lock using SET NX EX.

    Returns True if the lock was acquired, False otherwise.
    """
    client = get_redis()
    return bool(await client.set(key, "1", nx=True, ex=ttl))


async def release_lock(key: str) -> None:
    """Release a distributed lock by deleting the key."""
    client = get_redis()
    await client.delete(key)
