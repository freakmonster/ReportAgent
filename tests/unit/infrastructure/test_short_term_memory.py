"""Unit tests for short_term_memory module."""

from __future__ import annotations

import pytest

from infrastructure.memory.short_term import format_context


class TestFormatContext:
    """Verify format_context behaviour with various inputs."""

    @pytest.mark.asyncio
    async def test_format_context_normal(self):
        """正常情况：拼接多个主题"""
        entries = [
            {"query": "AI行业动态2026"},
            {"query": "芯片半导体供应链"},
            {"query": "新能源投资趋势"},
        ]
        result = await format_context(entries)
        assert "用户最近关注的主题：" in result
        assert "AI行业动态2026" in result
        assert "芯片半导体供应链" in result

    @pytest.mark.asyncio
    async def test_format_context_truncation(self):
        """query 过长时截断到 30 字符"""
        entries = [{"query": "A" * 100}]
        result = await format_context(entries)
        assert len(result) < 150  # 30 char truncation + prefix

    @pytest.mark.asyncio
    async def test_format_context_empty(self):
        """空列表返回空字符串"""
        result = await format_context([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_format_context_single(self):
        """单条记录"""
        result = await format_context([{"query": "测试主题"}])
        assert "测试主题" in result
