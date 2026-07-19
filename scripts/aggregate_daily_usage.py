"""Aggregate daily usage stats from Redis to PostgreSQL.

Usage:
    python -m scripts.aggregate_daily_usage [--date YYYY-MM-DD]
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone


# ── Date parsing ─────────────────────────────────────────────────────────


def _parse_date() -> str:
    """Parse --date argument, defaulting to yesterday (UTC)."""
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        return sys.argv[idx + 1]
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


# ── Models tracked ───────────────────────────────────────────────────────

MODELS = ["deepseek-flash", "deepseek-pro", "qwen-8b", "qwen-32b", "qwen-max"]


# ── Percentile helper ────────────────────────────────────────────────────


def _percentile(data: list[float], p: int) -> float:
    """Calculate percentile using nearest-rank method."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


# ── Main aggregation logic ───────────────────────────────────────────────


async def aggregate(target_date: str) -> None:
    """Aggregate a single day's usage stats from Redis → PostgreSQL.

    For each model, reads counters and duration samples from Redis,
    computes percentiles, upserts into the ``usage_daily`` table,
    and cleans up the Redis keys.
    """
    # Lazy imports to avoid global-side side effects
    from config.settings import settings
    from infrastructure.cache.redis_client import close_redis, get_redis, init_redis
    from infrastructure.database.connection import _get_session_factory, close_db, init_db
    from sqlalchemy import text

    # Initialize connections
    await init_redis()
    await init_db()

    redis = get_redis()
    factory = _get_session_factory()

    async with factory() as session:
        for model in MODELS:
            req_key = f"stats:daily:{target_date}:requests:{model}"
            token_key = f"stats:daily:{target_date}:tokens:{model}"
            dur_key = f"stats:daily:{target_date}:durations:{model}"

            request_count = int(await redis.get(req_key) or 0)
            total_tokens = int(await redis.get(token_key) or 0)
            duration_strs = await redis.lrange(dur_key, 0, -1)
            durations = [float(d) for d in duration_strs]

            if not request_count and not durations:
                continue

            avg_ms = sum(durations) / len(durations) if durations else 0.0
            p50 = _percentile(durations, 50)
            p95 = _percentile(durations, 95)

            await session.execute(
                text(
                    """
                    INSERT INTO usage_daily
                        (date, model, request_count, success_count,
                         total_tokens, avg_duration_ms, p50_duration_ms, p95_duration_ms)
                    VALUES
                        (:date, :model, :req, :req, :tokens, :avg, :p50, :p95)
                    ON CONFLICT (date, model) DO UPDATE SET
                        request_count = usage_daily.request_count + :req,
                        total_tokens = usage_daily.total_tokens + :tokens,
                        avg_duration_ms = :avg,
                        p50_duration_ms = :p50,
                        p95_duration_ms = :p95
                    """
                ),
                {
                    "date": target_date,
                    "model": model,
                    "req": request_count,
                    "tokens": total_tokens,
                    "avg": avg_ms,
                    "p50": p50,
                    "p95": p95,
                },
            )

            # Clean up Redis keys
            await redis.delete(req_key, token_key, dur_key)
            print(
                f"[aggregate] {target_date} {model}: "
                f"{request_count} reqs, {total_tokens} tokens, "
                f"p50={p50:.0f}ms p95={p95:.0f}ms",
                flush=True,
            )

        await session.commit()

    await close_db()
    await close_redis()
    print(f"[aggregate] {target_date} done", flush=True)


# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(aggregate(_parse_date()))
