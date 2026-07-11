"""Redis sliding window rate limiter middleware."""

from __future__ import annotations

import time

from fastapi import Request, HTTPException


class RateLimitMiddleware:
    """Sliding-window rate limiter by user ID.

    Uses a simple in-memory counter for dev (production would use Redis).
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.app = app
        self._max_requests = max_requests
        self._window = window_seconds
        self._counters: dict[str, list[float]] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        user_id = getattr(request.state, "user_id", "anonymous")

        # Clean old entries
        now = time.time()
        if user_id not in self._counters:
            self._counters[user_id] = []
        self._counters[user_id] = [
            t for t in self._counters[user_id] if now - t < self._window
        ]

        if len(self._counters[user_id]) >= self._max_requests:
            from fastapi.responses import JSONResponse
            response = JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
            await response(scope, receive, send)
            return

        self._counters[user_id].append(now)
        await self.app(scope, receive, send)
