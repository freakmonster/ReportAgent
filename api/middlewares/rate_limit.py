"""Redis sliding window rate limiter middleware.

Uses Redis ZSET for a multi-instance-safe sliding window.
Falls back to in-memory dict when Redis is unavailable.
"""

from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse


class RateLimitMiddleware:
    """Sliding-window rate limiter by user ID.

    Primary backend: Redis ZSET (key = ``ratelimit:{user_id}``).
    Fallback backend: in-memory ``dict`` (single-instance, process-local).
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.app = app
        self._max_requests = max_requests
        self._window = window_seconds
        # In-memory fallback counters for when Redis is unavailable
        self._fallback_counters: dict[str, list[float]] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        user_id = getattr(request.state, "user_id", "anonymous")

        # Try Redis path first
        try:
            from infrastructure.cache.redis_client import get_redis

            redis = get_redis()
            key = f"ratelimit:{user_id}"
            now = time.time()
            window_start = now - self._window

            # Atomic cleanup + count in a single round-trip
            pipe = redis.pipeline(transaction=True)
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            results = await pipe.execute()
            count = results[1]  # ZCARD result

            if count >= self._max_requests:
                response = JSONResponse(
                    status_code=429, content={"detail": "Rate limit exceeded"}
                )
                await response(scope, receive, send)
                return

            await redis.zadd(key, {str(now): now})
            await redis.expire(key, int(self._window) + 1)

        except Exception:
            # Redis unavailable → fall back to in-memory sliding window
            await self._fallback_check(scope, receive, send, user_id)
            return

        await self.app(scope, receive, send)

    async def _fallback_check(
        self, scope, receive, send, user_id: str
    ) -> None:
        """In-memory sliding window fallback when Redis is unreachable."""
        now = time.time()
        if user_id not in self._fallback_counters:
            self._fallback_counters[user_id] = []
        self._fallback_counters[user_id] = [
            t for t in self._fallback_counters[user_id]
            if now - t < self._window
        ]
        if len(self._fallback_counters[user_id]) >= self._max_requests:
            response = JSONResponse(
                status_code=429, content={"detail": "Rate limit exceeded"}
            )
            await response(scope, receive, send)
            return
        self._fallback_counters[user_id].append(now)
        await self.app(scope, receive, send)
