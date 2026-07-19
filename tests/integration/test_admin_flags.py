"""Integration tests for Admin API — feature flag management endpoints."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


class TestAdminFeatureFlags:
    """Verify /admin/flags CRUD operations."""

    def test_list_flags_returns_all(self) -> None:
        """GET /admin/flags returns all flags with names and states."""
        r = client.get("/admin/flags")
        assert r.status_code == 200
        data = r.json()
        assert "flags" in data
        assert "total" in data
        assert data["total"] >= 5
        # Spot-check key flags exist
        assert "reranker_enabled" in data["flags"]
        assert "rag_enabled" in data["flags"]

    def test_list_flags_items_have_required_fields(self) -> None:
        """Each flag item has name, enabled, source."""
        r = client.get("/admin/flags")
        data = r.json()
        for item in data["flags"].values():
            assert "name" in item
            assert "enabled" in item
            assert "source" in item
            assert item["source"] in ("default", "redis")

    def test_get_single_flag(self) -> None:
        """GET /admin/flags/rag_enabled returns a valid flag."""
        r = client.get("/admin/flags/rag_enabled")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "rag_enabled"
        assert isinstance(data["enabled"], bool)

    def test_get_unknown_flag_404(self) -> None:
        """GET /admin/flags/nonexistent returns 404."""
        r = client.get("/admin/flags/nonexistent_flag_xyz")
        assert r.status_code == 404

    def test_update_flag_toggle(self) -> None:
        """PUT /admin/flags/rag_enabled toggles the flag."""
        r = client.put(
            "/admin/flags/rag_enabled",
            json={"enabled": False},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "rag_enabled"
        assert data["enabled"] is False
        assert "message" in data

    def test_update_unknown_flag_404(self) -> None:
        """PUT /admin/flags/unknown returns 404."""
        r = client.put("/admin/flags/unknown_xyz", json={"enabled": True})
        assert r.status_code == 404

    def test_reset_flag_reverts_to_default(self) -> None:
        """DELETE /admin/flags/rag_enabled resets to default."""
        r = client.delete("/admin/flags/rag_enabled")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "rag_enabled"
        assert "reset_to" in data
        assert isinstance(data["reset_to"], bool)

    def test_reset_unknown_flag_404(self) -> None:
        """DELETE /admin/flags/unknown returns 404."""
        r = client.delete("/admin/flags/unknown_xyz")
        assert r.status_code == 404

    def test_update_invalid_body_422(self) -> None:
        """PUT with missing 'enabled' field returns 422."""
        r = client.put("/admin/flags/rag_enabled", json={})
        assert r.status_code == 422

    def test_update_invalid_type_422(self) -> None:
        """PUT with non-boolean value returns 422."""
        r = client.put("/admin/flags/rag_enabled", json={"enabled": 123})
        assert r.status_code == 422


class TestAdminStatus:
    """Verify /admin/status endpoint."""

    def test_system_status_basic(self) -> None:
        """GET /admin/status returns app info."""
        r = client.get("/admin/status")
        assert r.status_code == 200
        data = r.json()
        assert "app_name" in data
        assert "app_version" in data
        assert "environment" in data
        assert "feature_flags" in data
        assert "services" in data

    def test_system_status_feature_flags(self) -> None:
        """Feature flags in status response match /admin/flags."""
        r_status = client.get("/admin/status")
        r_flags = client.get("/admin/flags")

        status_flags = r_status.json()["feature_flags"]
        flags_data = r_flags.json()["flags"]

        for name in flags_data:
            assert name in status_flags
            assert isinstance(status_flags[name], bool)
