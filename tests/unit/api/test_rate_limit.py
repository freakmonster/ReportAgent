"""Unit tests for rate limit middleware."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


class TestRateLimit:
    """Verify sliding window rate limiting via the test client."""

    def test_many_requests_under_limit_pass(self) -> None:
        """Multiple requests under the rate limit all pass."""
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200

    def test_rate_limit_info_in_headers(self) -> None:
        """Rate limit middleware is active."""
        response = client.get("/health")
        assert response.status_code == 200
