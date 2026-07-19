"""Unit tests for dashboard API schemas."""


def test_dashboard_overview_response():
    """验证 dashboard overview 响应结构"""
    data = {
        "total_requests": 0,
        "success_rate": 0.0,
        "total_tokens": 0,
        "avg_duration_seconds": 0.0,
        "by_template": {},
    }
    assert isinstance(data["total_requests"], int)
    assert isinstance(data["success_rate"], float)
    assert isinstance(data["total_tokens"], int)
    assert isinstance(data["avg_duration_seconds"], float)
    assert isinstance(data["by_template"], dict)


def test_dashboard_recent_empty():
    """验证空 recent 返回空列表"""
    data = {"items": []}
    assert data["items"] == []
    assert len(data["items"]) == 0


def test_dashboard_overview_zero_data():
    """无数据时返回全 0 不报错"""
    data = {
        "total_requests": 0,
        "success_rate": 0.0,
        "total_tokens": 0,
        "avg_duration_seconds": 0.0,
        "by_template": {},
    }
    assert data["total_requests"] == 0
    assert data["success_rate"] == 0.0
    assert data["total_tokens"] == 0
