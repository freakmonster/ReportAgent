"""Unit tests for task router — status queries and human review."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


class TestTaskRouter:
    """Verify task management endpoints."""

    def test_get_task_status_unknown(self) -> None:
        response = client.get("/task/unknown-wf-id")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unknown"

    def test_submit_human_review(self) -> None:
        response = client.post(
            "/task/review",
            json={"workflow_id": "wf-review-1", "decision": "approved", "comment": "ok"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True

    def test_double_submit_review_returns_409(self) -> None:
        """V2.1: Second submission for same workflow returns 409 Conflict."""
        wf_id = "wf-double-1"
        # First submission
        client.post("/task/review", json={"workflow_id": wf_id, "decision": "approved"})
        # Second submission — should be rejected
        response = client.post("/task/review", json={"workflow_id": wf_id, "decision": "rejected"})
        assert response.status_code == 409

    def test_invalid_decision_rejected(self) -> None:
        response = client.post(
            "/task/review",
            json={"workflow_id": "wf-1", "decision": "maybe"},
        )
        assert response.status_code == 422
