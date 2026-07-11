"""Unit tests for chat router SSE streaming."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


class TestChatRouter:
    """Verify SSE chat streaming endpoint."""

    def test_chat_stream_returns_events(self) -> None:
        response = client.post(
            "/chat/stream",
            json={"query": "test report", "report_type": "deep_report", "user_id": "u1"},
        )
        assert response.status_code == 200
        # SSE responses are text/event-stream
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_chat_stream_invalid_report_type_rejected(self) -> None:
        response = client.post(
            "/chat/stream",
            json={"query": "test", "report_type": "invalid", "user_id": "u1"},
        )
        assert response.status_code == 422

    def test_chat_stream_empty_query_rejected(self) -> None:
        response = client.post(
            "/chat/stream",
            json={"query": "", "user_id": "u1"},
        )
        assert response.status_code == 422
