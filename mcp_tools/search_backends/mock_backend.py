"""Mock search backend — deterministic results for development and testing.

Works without any external API, returns predictable structured results.
Configure via ``search_backend: mock`` in config YAML.
"""

from __future__ import annotations

from typing import Any

from .base import BaseSearchBackend

# Pre-baked mock results for common queries
_MOCK_RESULTS: list[dict[str, Any]] = [
    {
        "title": "Mock Search Result 1 — Industry Overview",
        "url": "https://example.com/research/mock-1",
        "content": "这是一份模拟的行业研究报告结果。根据行业数据显示，2025年市场规模持续扩大。",
        "score": 0.95,
    },
    {
        "title": "Mock Search Result 2 — Market Analysis",
        "url": "https://example.com/research/mock-2",
        "content": "模拟的市场分析结果。竞争格局稳定，前三大企业市场占有率达到60%。",
        "score": 0.88,
    },
    {
        "title": "Mock Search Result 3 — Policy Update",
        "url": "https://example.com/research/mock-3",
        "content": "模拟的政策动态结果。近期出台了多项支持行业发展的政策措施。",
        "score": 0.82,
    },
    {
        "title": "Mock Search Result 4 — Technology Trends",
        "url": "https://example.com/research/mock-4",
        "content": "模拟的技术趋势分析。AI和自动化技术正在重塑行业格局。",
        "score": 0.76,
    },
    {
        "title": "Mock Search Result 5 — Financial Data",
        "url": "https://example.com/research/mock-5",
        "content": "模拟的财务数据分析。行业平均毛利率维持在30%左右的健康水平。",
        "score": 0.71,
    },
]

_MOCK_NEWS: list[dict[str, Any]] = [
    {
        "title": "Mock News — 行业龙头企业发布年度报告",
        "url": "https://example.com/news/mock-news-1",
        "content": "行业龙头企业近日发布了年度报告，营收同比增长15%，超出市场预期。",
        "score": 0.92,
    },
    {
        "title": "Mock News — 新技术突破推动产业升级",
        "url": "https://example.com/news/mock-news-2",
        "content": "最新技术突破有望推动整个产业链升级，多家企业已开始布局。",
        "score": 0.85,
    },
]

_MOCK_ACADEMIC: list[dict[str, Any]] = [
    {
        "title": "Mock Academic — 行业发展趋势实证研究",
        "url": "https://example.com/academic/mock-paper-1",
        "content": "本文通过实证研究方法，系统分析了近五年行业发展规律，发现数字化转型显著提升了企业效率。",
        "score": 0.90,
    },
    {
        "title": "Mock Academic — 产业政策效果评估",
        "url": "https://example.com/academic/mock-paper-2",
        "content": "采用双重差分法评估了产业政策的效果，结果表明政策显著促进了行业创新。",
        "score": 0.83,
    },
]


class MockSearchBackend(BaseSearchBackend):
    """Deterministic mock search backend for development and testing.

    Returns pre-defined results without any external API calls.
    Useful for CI/CD pipelines and local development without network access.
    """

    async def web_search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Return mock web search results, limited by max_results."""
        return _MOCK_RESULTS[: min(max_results, len(_MOCK_RESULTS))]

    async def news_search(
        self,
        query: str,
        max_results: int = 10,
        days: int = 7,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Return mock news search results."""
        return _MOCK_NEWS[: min(max_results, len(_MOCK_NEWS))]

    async def academic_search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Return mock academic search results."""
        return _MOCK_ACADEMIC[: min(max_results, len(_MOCK_ACADEMIC))]

    @property
    def name(self) -> str:
        return "mock"
