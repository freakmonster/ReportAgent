"""Unit tests for health router."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


class TestHealthRouter:
    """Verify health endpoint responses."""

    def test_health_returns_200(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "services" in data

    def test_health_has_service_keys(self) -> None:
        response = client.get("/health")
        data = response.json()
        services = data.get("services", {})
        assert "postgresql" in services
        assert "redis" in services
        assert "qdrant" in services
