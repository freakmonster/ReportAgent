"""Unit tests for API schemas — request/response validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from api.schemas.request import ChatRequest, HumanReviewRequest, TaskStatusRequest  # noqa: E402
from api.schemas.response import ErrorResponse, HealthResponse, TaskStatusResponse  # noqa: E402


class TestChatRequest:
    """Verify ChatRequest validation."""

    def test_valid_request(self) -> None:
        req = ChatRequest(query="test", report_type="deep_report", user_id="u1")
        assert req.query == "test"
        assert req.report_type == "deep_report"

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChatRequest(query="")

    def test_invalid_report_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChatRequest(query="x", report_type="invalid_type")

    def test_default_values(self) -> None:
        req = ChatRequest(query="hello")
        assert req.report_type == "deep_report"
        assert req.user_id == "anonymous"

    def test_too_long_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChatRequest(query="x" * 5001)


class TestHumanReviewRequest:
    """Verify HumanReviewRequest validation."""

    def test_valid_decision(self) -> None:
        for d in ("approved", "rejected", "needs_changes"):
            req = HumanReviewRequest(workflow_id="wf-1", decision=d)
            assert req.decision == d

    def test_invalid_decision_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HumanReviewRequest(workflow_id="wf-1", decision="maybe")


class TestTaskStatusRequest:
    """Verify TaskStatusRequest validation."""

    def test_valid(self) -> None:
        req = TaskStatusRequest(workflow_id="wf-1")
        assert req.workflow_id == "wf-1"


class TestResponseModels:
    """Verify response models."""

    def test_error_response_with_code(self) -> None:
        err = ErrorResponse(code=4001, message="Invalid input")
        assert err.code == 4001
        assert err.error is True

    def test_health_response(self) -> None:
        resp = HealthResponse(status="ok", services={"pg": "connected"}, version="0.1.0")
        assert resp.status == "ok"
        assert resp.services["pg"] == "connected"

    def test_task_status_response(self) -> None:
        resp = TaskStatusResponse(workflow_id="wf-1", status="writing", retry_count=1)
        assert resp.status == "writing"
