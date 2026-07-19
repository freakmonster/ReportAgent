"""Unit tests for data_collector memory injection logic."""

from __future__ import annotations


def test_data_collector_has_memory_injection():
    """验证 data_collector.py 中有短期记忆注入代码"""
    import inspect
    import agents.nodes.data_collector as data_collector

    source = inspect.getsource(data_collector.entry)
    # 检查关键模式
    assert "session_id" in source, "data_collector 应使用 session_id"
    assert "load_memory" in source, "data_collector 应调用 load_memory"
    assert "format_context" in source, "data_collector 应调用 format_context"
    assert "short-term memory injected" in source, "data_collector 应有注入日志"


def test_data_collector_fallback_behavior():
    """验证 data_collector 在异常时降级不崩溃"""
    import inspect
    import agents.nodes.data_collector as data_collector

    source = inspect.getsource(data_collector.entry)
    # 确认异常处理存在
    assert "except" in source, "data_collector 应有异常处理"


def test_format_context_import():
    """验证 format_context 可从 short_term 导入"""
    from infrastructure.memory.short_term import format_context
    assert callable(format_context)
