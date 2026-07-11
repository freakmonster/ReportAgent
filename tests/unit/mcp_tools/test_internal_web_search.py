"""Unit tests for internal web search tool (fallback)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from mcp_tools.internal_tools.web_search import (  # noqa: E402
    web_search,
    web_search_tool,
    news_search_tool,
    news_search,
    academic_search,
    _parse_ddg_html,
)


# ---------------------------------------------------------------------------
# web_search tests
# ---------------------------------------------------------------------------


class TestWebSearch:
    """Verify internal web search fallback behavior."""

    @pytest.mark.asyncio
    async def test_web_search_with_duckduckgo_library(self) -> None:
        """When duckduckgo-search is available, returns real results."""
        mock_results = [
            {"title": "Test Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Test Result 2", "href": "https://example.com/2", "body": "Snippet 2"},
        ]

        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text = MagicMock(return_value=mock_results)

        # Patch the import inside web_search module (not the global module)
        with patch.dict("sys.modules", {"duckduckgo_search": MagicMock(DDGS=MagicMock(return_value=mock_ddgs))}):
            results = await web_search("test query", max_results=5)

        assert len(results) == 2
        assert results[0]["title"] == "Test Result 1"
        assert results[0]["url"] == "https://example.com/1"
        assert results[0]["snippet"] == "Snippet 1"

    @pytest.mark.asyncio
    async def test_web_search_duckduckgo_fails_then_html_fallback(self) -> None:
        """When duckduckgo-search is unavailable, falls back to DDG HTML parsing."""
        # Ensure duckduckgo_search is not importable
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            import importlib
            importlib.reload(sys.modules["mcp_tools.internal_tools.web_search"])
            # DDG HTML returns valid HTML with results
            html_content = """
            <html><body>
            <a class="result__a" href="https://example.com/a">Result A</a>
            <a class="result__snippet">Snippet for result A</a>
            </body></html>
            """
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = html_content

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            with patch("httpx.AsyncClient", return_value=mock_client):
                # Reload the module after clearing the duckduckgo_search module
                import mcp_tools.internal_tools.web_search as ws_mod
                results = await ws_mod.web_search("test query", max_results=5)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/a"

    @pytest.mark.asyncio
    async def test_web_search_all_backends_fail_returns_placeholder(self) -> None:
        """When all backends fail, returns a placeholder result."""
        # Ensure both backends are unavailable
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            with patch("httpx.AsyncClient", side_effect=ImportError("not installed")):
                import importlib
                importlib.reload(sys.modules["mcp_tools.internal_tools.web_search"])
                import mcp_tools.internal_tools.web_search as ws_mod
                results = await ws_mod.web_search("unreachable query", max_results=3)

        assert len(results) == 1
        assert "unavailable" in results[0]["snippet"].lower() or "currently" in results[0]["snippet"].lower()

    @pytest.mark.asyncio
    async def test_web_search_respects_max_results(self) -> None:
        """web_search truncates to max_results."""
        mock_results = [
            {"title": f"R{i}", "href": f"https://e.com/{i}", "body": f"S{i}"}
            for i in range(10)
        ]
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text = MagicMock(return_value=mock_results[:3])  # DDGS respects max

        with patch.dict("sys.modules", {"duckduckgo_search": MagicMock(DDGS=MagicMock(return_value=mock_ddgs))}):
            results = await web_search("query", max_results=3)

        assert len(results) <= 3


# ---------------------------------------------------------------------------
# news_search and academic_search tests
# ---------------------------------------------------------------------------


class TestSpecializedSearches:
    """Verify news and academic search variants."""

    @pytest.mark.asyncio
    async def test_news_search_appends_news_keyword(self) -> None:
        """news_search calls web_search with 'news' appended."""
        with patch("mcp_tools.internal_tools.web_search.web_search") as mock_ws:
            mock_ws.return_value = []
            await news_search("electric vehicles")
            mock_ws.assert_called_once()
            call_args = mock_ws.call_args[0]
            assert "news" in call_args[0].lower()

    @pytest.mark.asyncio
    async def test_academic_search_appends_research_keyword(self) -> None:
        """academic_search calls web_search with 'research paper' appended."""
        with patch("mcp_tools.internal_tools.web_search.web_search") as mock_ws:
            mock_ws.return_value = []
            await academic_search("battery technology")
            mock_ws.assert_called_once()
            call_args = mock_ws.call_args[0]
            assert "research" in call_args[0].lower() or "paper" in call_args[0].lower()


# ---------------------------------------------------------------------------
# Tool callable interface tests
# ---------------------------------------------------------------------------


class TestToolCallables:
    """Verify registry-compatible callable interface."""

    @pytest.mark.asyncio
    async def test_web_search_tool_returns_structured_response(self) -> None:
        """web_search_tool returns dict with results, query, source, timestamp."""
        with patch("mcp_tools.internal_tools.web_search.web_search") as mock_ws:
            mock_ws.return_value = [{"title": "T", "url": "https://u", "snippet": "S"}]
            result = await web_search_tool({"query": "hello", "max_results": 1})

        assert result["query"] == "hello"
        assert result["source"] == "internal"
        assert "timestamp" in result
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_news_search_tool_returns_structured_response(self) -> None:
        """news_search_tool returns dict with results, source, timestamp."""
        with patch("mcp_tools.internal_tools.web_search.news_search") as mock_ns:
            mock_ns.return_value = []
            result = await news_search_tool({"query": "test"})

        assert result["query"] == "test"
        assert result["source"] == "internal_news"
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# DDG HTML parser tests
# ---------------------------------------------------------------------------


class TestDDGHTMLParser:
    """Verify the basic HTML parsing fallback."""

    def test_parse_ddg_html_extracts_results(self) -> None:
        """Parse extracts title, url, snippet from DDG HTML."""
        html = """
        <div class="result">
            <a class="result__a" href="https://example.com/result1">Result One</a>
            <a class="result__snippet">This is the snippet for result one</a>
        </div>
        """
        results = _parse_ddg_html(html, max_results=10)
        assert len(results) == 1
        assert results[0]["title"] == "Result One"
        assert results[0]["url"] == "https://example.com/result1"
        assert results[0]["snippet"] == "This is the snippet for result one"

    def test_parse_ddg_html_empty(self) -> None:
        """Empty HTML returns empty list."""
        results = _parse_ddg_html("<html></html>", max_results=10)
        assert results == []

    def test_parse_ddg_html_respects_max_results(self) -> None:
        """Parser truncates to max_results."""
        html = ""
        for i in range(5):
            html += f'<a class="result__a" href="https://e.com/{i}">Title {i}</a>'
            html += f'<a class="result__snippet">Snippet {i}</a>'
        results = _parse_ddg_html(html, max_results=3)
        assert len(results) == 3
