"""Unit tests for task router — status queries and human review."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_state():
    """Set checkpointer + workflow_repo on app state to avoid PG dependency."""
    # Mock checkpointer so submit_human_review doesn't 503
    app.state.checkpointer = MagicMock()

    # Mock the workflow_repo singleton so get_by_id / approve_with_lock work
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = None  # default: no record found
    mock_repo.approve_with_lock.return_value = True
    mock_repo.reject_with_lock.return_value = True

    with patch(
        "infrastructure.database.repositories.workflow_repo.get_workflow_repo",
        return_value=mock_repo,
    ):
        yield


client = TestClient(app)


class TestTaskRouter:
    """Verify task management endpoints."""

    def test_get_task_status_unknown(self) -> None:
        response = client.get("/task/unknown-wf-id")
        # No record found → "unknown" status
        assert response.status_code == 200

    def test_submit_human_review_requires_checkpointer(self) -> None:
        """Without checkpointer on app.state, returns 503."""
        # Clear checkpointer
        old = app.state.checkpointer
        app.state.checkpointer = None
        response = client.post(
            "/task/review",
            json={"workflow_id": "wf-review-1", "decision": "approved", "comment": "ok"},
        )
        assert response.status_code == 503
        app.state.checkpointer = old

    def test_invalid_decision_rejected(self) -> None:
        response = client.post(
            "/task/review",
            json={"workflow_id": "wf-1", "decision": "maybe"},
        )
        assert response.status_code == 422
