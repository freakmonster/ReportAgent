"""E2E test — API-level test for the complete workflow."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


class TestHealthCheck:
    """Verify basic service health."""

    def test_health_returns_200(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestChatFlow:
    """Verify SSE chat streaming."""

    def test_chat_stream_valid_request(self) -> None:
        response = client.post(
            "/chat/stream",
            json={"query": "test", "report_type": "deep_report", "user_id": "u1"},
        )
        assert response.status_code == 200
        assert "event-stream" in response.headers.get("content-type", "")

    def test_chat_stream_invalid_type_rejected(self) -> None:
        response = client.post(
            "/chat/stream",
            json={"query": "test", "report_type": "invalid"},
        )
        assert response.status_code == 422


class TestTaskFlow:
    """Verify task management flow."""

    def test_workflow_lifecycle(self) -> None:
        """Complete workflow: query → review → status check."""
        # Query status
        response = client.get("/task/wf-e2e-1")
        assert response.status_code == 200

        # Submit review
        response = client.post(
            "/task/review",
            json={"workflow_id": "wf-e2e-1", "decision": "approved"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True

    def test_double_submit_returns_409(self) -> None:
        """V2.1: Double submit protection."""
        wf_id = "wf-double-e2e"
        client.post("/task/review", json={"workflow_id": wf_id, "decision": "approved"})
        response = client.post("/task/review", json={"workflow_id": wf_id, "decision": "rejected"})
        assert response.status_code == 409
