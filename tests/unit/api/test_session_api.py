"""Unit tests for session API schemas."""

from __future__ import annotations

from api.schemas.session import CreateSessionRequest, SessionListResponse, SessionResponse


def test_create_session_request_with_title():
    """带 title 创建"""
    req = CreateSessionRequest(user_id="u1", title="测试会话")
    assert req.user_id == "u1"
    assert req.title == "测试会话"


def test_create_session_request_without_title():
    """不带 title 创建（默认 None，API 层处理）"""
    req = CreateSessionRequest(user_id="u1")
    assert req.title is None


def test_session_response_serialization():
    """SessionResponse 序列化"""
    resp = SessionResponse(
        session_id="s1",
        user_id="u1",
        title="测试",
        status="active",
        report_count=0,
        created_at="2026-07-19T00:00:00Z",
        updated_at="2026-07-19T00:00:00Z",
    )
    data = resp.model_dump()
    assert data["session_id"] == "s1"
    assert data["status"] == "active"


def test_session_list_response():
    """SessionListResponse 序列化"""
    items = [
        SessionResponse(
            session_id="s1", user_id="u1", title="S1",
            status="active", report_count=1,
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        ),
        SessionResponse(
            session_id="s2", user_id="u1", title="S2",
            status="active", report_count=2,
            created_at="2026-01-02T00:00:00Z", updated_at="2026-01-02T00:00:00Z",
        ),
    ]
    resp = SessionListResponse(sessions=items, total=2)
    assert resp.total == 2
    assert len(resp.sessions) == 2
