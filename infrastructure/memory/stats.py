"""LLM usage statistics stored in Redis with TTL.

All operations are fire-and-forget: failures are logged to stderr
but never raised, so callers can safely wrap them in try/except.
"""

import sys
from datetime import datetime

_TTL_SECONDS = 31 * 86400  # 31 days


async def incr_llm_request(model: str) -> None:
    """Increment the daily request counter for a model (TTL 31 days)."""
    try:
        from infrastructure.cache.redis_client import get_redis

        date = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"stats:daily:{date}:requests:{model}"
        redis = get_redis()
        await redis.incr(key)
        await redis.expire(key, _TTL_SECONDS)
    except Exception as exc:
        print(
            f"[stats] incr_llm_request({model!r}) failed: {exc}",
            file=sys.stderr,
            flush=True,
        )


async def incr_llm_tokens(model: str, tokens: int) -> None:
    """Increment the daily token counter for a model (TTL 31 days)."""
    try:
        from infrastructure.cache.redis_client import get_redis

        date = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"stats:daily:{date}:tokens:{model}"
        redis = get_redis()
        await redis.incrby(key, tokens)
        await redis.expire(key, _TTL_SECONDS)
    except Exception as exc:
        print(
            f"[stats] incr_llm_tokens({model!r}, {tokens}) failed: {exc}",
            file=sys.stderr,
            flush=True,
        )


async def record_workflow_duration(model: str, duration_ms: float) -> None:
    """Push a workflow duration (ms) onto a per-model daily list (TTL 31 days)."""
    try:
        from infrastructure.cache.redis_client import get_redis

        date = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"stats:daily:{date}:durations:{model}"
        redis = get_redis()
        await redis.lpush(key, str(duration_ms))
        await redis.expire(key, _TTL_SECONDS)
    except Exception as exc:
        print(
            f"[stats] record_workflow_duration({model!r}, {duration_ms}) failed: {exc}",
            file=sys.stderr,
            flush=True,
        )
