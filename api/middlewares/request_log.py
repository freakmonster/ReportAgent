"""Structured JSON request logging middleware with TraceID injection."""

from __future__ import annotations

import time
import uuid

from fastapi import Request


class RequestLogMiddleware:
    """Log every request with structured JSON format + TraceID."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        trace_id = str(uuid.uuid4())[:8]
        request.state.trace_id = trace_id
        start = time.time()

        # Wrap send to capture response status
        async def _send(message):
            if message["type"] == "http.response.start":
                nonlocal start
                elapsed = (time.time() - start) * 1000
                from infrastructure.observability.logger import get_logger

                logger = get_logger("api.request")
                logger.info(
                    "request",
                    trace_id=trace_id,
                    method=request.method,
                    path=request.url.path,
                    status=message.get("status", 0),
                    duration_ms=round(elapsed, 2),
                )
            await send(message)

        await self.app(scope, receive, _send)
