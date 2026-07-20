"""Tests for pluggable search backends — Tavily, Mock, and factory."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402

from mcp_tools.search_backends.base import BaseSearchBackend  # noqa: E402
from mcp_tools.search_backends.mock_backend import (  # noqa: E402
    _MOCK_ACADEMIC,
    _MOCK_NEWS,
    _MOCK_RESULTS,
    MockSearchBackend,
)
from mcp_tools.search_backends.tavily_backend import TavilySearchBackend  # noqa: E402


class TestBaseSearchBackend:
    """Verify ABC interface requirements."""

    def test_abc_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            BaseSearchBackend()  # type: ignore[abstract]

    def test_abc_methods_defined(self) -> None:
        for method in ("web_search", "news_search", "academic_search"):
            assert hasattr(BaseSearchBackend, method)
            assert callable(getattr(BaseSearchBackend, method))


class TestMockSearchBackend:
    """Verify deterministic mock backend."""

    @pytest.mark.asyncio
    async def test_web_search_returns_results(self) -> None:
        backend = MockSearchBackend()
        results = await backend.web_search("测试查询")
        assert len(results) > 0
        assert all("title" in r for r in results)
        assert all("url" in r for r in results)
        assert all("content" in r for r in results)

    @pytest.mark.asyncio
    async def test_web_search_respects_max_results(self) -> None:
        backend = MockSearchBackend()
        results = await backend.web_search("test", max_results=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_news_search_returns_results(self) -> None:
        backend = MockSearchBackend()
        results = await backend.news_search("新闻", max_results=1)
        assert len(results) == 1
        assert "Mock News" in results[0]["title"]

    @pytest.mark.asyncio
    async def test_academic_search_returns_results(self) -> None:
        backend = MockSearchBackend()
        results = await backend.academic_search("学术", max_results=1)
        assert len(results) == 1
        assert "Mock Academic" in results[0]["title"]

    def test_name_is_mock(self) -> None:
        assert MockSearchBackend().name == "mock"

    @pytest.mark.asyncio
    async def test_clipped_to_max_results(self) -> None:
        backend = MockSearchBackend()
        results = await backend.web_search("q", max_results=100)
        assert len(results) == len(_MOCK_RESULTS)  # capped at mock data length


class TestTavilySearchBackend:
    """Verify Tavily backend interface and error handling."""

    def test_name_is_tavily(self) -> None:
        assert TavilySearchBackend().name == "tavily"

    @pytest.mark.asyncio
    async def test_web_search_no_api_key_returns_empty(self) -> None:
        """Without API key, Tavily backend returns empty results gracefully."""
        backend = TavilySearchBackend()
        # Reset any cached client
        TavilySearchBackend._client = None
        with patch.object(
            backend.__class__,
            "_get_client",
            side_effect=RuntimeError("TAVILY_API_KEY is not set"),
        ):
            results = await backend.web_search("test")
            assert results == []

    @pytest.mark.asyncio
    async def test_web_search_handles_api_error(self) -> None:
        backend = TavilySearchBackend()
        TavilySearchBackend._client = None
        with patch.object(
            backend.__class__,
            "_get_client",
            side_effect=Exception("Network error"),
        ):
            results = await backend.web_search("test")
            assert results == []


class TestSearchBackendFactory:
    """Verify factory function loads correct backend."""

    def test_factory_returns_backend(self) -> None:
        from mcp_tools.search_backends import get_search_backend

        backend = get_search_backend()
        assert isinstance(backend, (MockSearchBackend, TavilySearchBackend))

    def test_factory_returns_same_instance(self) -> None:
        from mcp_tools.search_backends import _cached_get_backend, get_search_backend

        _cached_get_backend.cache_clear()
        b1 = get_search_backend()
        b2 = get_search_backend()
        assert b1 is b2

    @pytest.mark.asyncio
    async def test_backend_implements_full_interface(self) -> None:
        """Any backend returned by the factory must implement all three search methods."""
        from mcp_tools.search_backends import _cached_get_backend, get_search_backend

        _cached_get_backend.cache_clear()
        backend = get_search_backend()

        # All three must be callable
        assert callable(backend.web_search)
        assert callable(backend.news_search)
        assert callable(backend.academic_search)

        # All three must return lists
        r1 = await backend.web_search("q", max_results=1)
        r2 = await backend.news_search("q", max_results=1)
        r3 = await backend.academic_search("q", max_results=1)
        assert isinstance(r1, list)
        assert isinstance(r2, list)
        assert isinstance(r3, list)
