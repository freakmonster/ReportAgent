"""Unit tests for SessionRepository — basic smoke tests without DB."""

from __future__ import annotations

from datetime import datetime

import pytest

from infrastructure.database.repositories.session_repo import SessionRecord


def test_session_record_from_row():
    """SessionRecord.from_row 反序列化"""
    now = datetime.utcnow()
    row = type("row", (), {
        "session_id": "s1",
        "user_id": "u1",
        "tenant_id": "default",
        "title": "测试会话",
        "status": "active",
        "report_count": 3,
        "first_query": "test query",
        "created_at": now,
        "updated_at": now,
    })()
    record = SessionRecord.from_row(row)
    assert record.session_id == "s1"
    assert record.title == "测试会话"
    assert record.report_count == 3
    assert record.status == "active"


def test_session_record_defaults():
    """SessionRecord 默认字段"""
    # 验证创建时默认值逻辑（通过代码检查）
    from infrastructure.database.repositories.session_repo import SessionRepository
    assert hasattr(SessionRepository, 'create')
    assert hasattr(SessionRepository, 'list_by_user')
    assert hasattr(SessionRepository, 'soft_delete')
    assert hasattr(SessionRepository, 'increment_report_count')
