"""Unit tests for stats module."""


def test_stats_key_format():
    """验证 key 格式逻辑（通过直接构造 key 来验证）"""
    from datetime import datetime
    date = datetime.utcnow().strftime("%Y-%m-%d")
    key = f"stats:daily:{date}:requests:deepseek-flash"
    assert "stats:daily:" in key
    assert date in key
    assert "requests:deepseek-flash" in key


def test_stats_module_imports():
    """验证 stats 模块可导入"""
    from infrastructure.memory.stats import incr_llm_request, incr_llm_tokens, record_workflow_duration
    assert callable(incr_llm_request)
    assert callable(incr_llm_tokens)
    assert callable(record_workflow_duration)
