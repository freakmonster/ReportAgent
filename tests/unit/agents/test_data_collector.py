"""Unit tests for data_collector node — Tavily Search + Extract with fallback."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402


class TestDataCollector:
    """Verify data_collector.entry() with mocked Tavily."""

    @pytest.mark.asyncio
    async def test_successful_search_and_extract(self):
        """Full Tavily path: search → extract → raw_docs."""
        mock_search = MagicMock(
            return_value={
                "results": [
                    {"title": "Title 1", "url": "https://a.com/1"},
                    {"title": "Title 2", "url": "https://a.com/2"},
                ]
            }
        )
        mock_extract = MagicMock(
            return_value={
                "results": [
                    {"url": "https://a.com/1", "raw_content": "Content 1"},
                    {"url": "https://a.com/2", "raw_content": "Content 2"},
                ],
                "failed_results": [],
            }
        )

        with (
            patch("agents.nodes.data_collector.TavilyClient") as mock_client_cls,
            patch("agents.nodes.data_collector.asyncio.to_thread") as mock_to_thread,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_to_thread.side_effect = [mock_search(), mock_extract()]

            from agents.nodes.data_collector import entry

            state = {
                "base": {"user_input": "test query", "template_name": "flash_news"},
                "collection": {"raw_docs": [], "compressed_summary": {}, "source_urls": []},
            }
            result = await entry(state)

        raw_docs = result["collection"]["raw_docs"]
        assert len(raw_docs) == 2
        assert raw_docs[0]["title"] == "Title 1"
        assert raw_docs[0]["url"] == "https://a.com/1"
        assert raw_docs[0]["content"] == "Content 1"
        assert raw_docs[1]["title"] == "Title 2"
        assert result["collection"]["source_urls"] == ["https://a.com/1", "https://a.com/2"]

    @pytest.mark.asyncio
    async def test_extract_failure_falls_back_to_url_loader(self):
        """When Tavily Extract fails, url_loader is used as fallback."""
        mock_search = MagicMock(
            return_value={
                "results": [
                    {"title": "Bad Site", "url": "https://bad.com/page"},
                ]
            }
        )
        mock_extract = MagicMock(
            return_value={
                "results": [],
                "failed_results": [{"url": "https://bad.com/page", "error": "timeout"}],
            }
        )

        mock_page = MagicMock()
        mock_page.url = "https://bad.com/page"
        mock_page.title = "Bad Site (scraped)"
        mock_page.text = "Scraped content"

        with (
            patch("agents.nodes.data_collector.TavilyClient") as mock_client_cls,
            patch("agents.nodes.data_collector.asyncio.to_thread") as mock_to_thread,
            patch("retrieval.loaders.url_loader.fetch_multiple") as mock_fetch,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_to_thread.side_effect = [mock_search(), mock_extract()]
            mock_fetch.return_value = [mock_page]

            from agents.nodes.data_collector import entry

            state = {
                "base": {"user_input": "test", "template_name": "deep_report"},
                "collection": {"raw_docs": [], "compressed_summary": {}, "source_urls": []},
            }
            result = await entry(state)

        raw_docs = result["collection"]["raw_docs"]
        assert len(raw_docs) == 1
        assert raw_docs[0]["content"] == "Scraped content"

    @pytest.mark.asyncio
    async def test_empty_user_input_returns_unchanged(self):
        """No query → skip search, return state as-is."""
        from agents.nodes.data_collector import entry

        state = {"base": {"user_input": ""}, "collection": {}}
        result = await entry(state)
        assert result == state

    @pytest.mark.asyncio
    async def test_flash_news_uses_news_topic(self):
        """flash_news template passes topic=news to search."""
        mock_search = MagicMock(return_value={"results": []})

        with (
            patch("agents.nodes.data_collector.TavilyClient") as mock_client_cls,
            patch("agents.nodes.data_collector.asyncio.to_thread") as mock_to_thread,
        ):
            mock_client_cls.return_value = MagicMock()
            mock_to_thread.return_value = mock_search()

            from agents.nodes.data_collector import entry

            state = {
                "base": {"user_input": "news", "template_name": "flash_news"},
                "collection": {"raw_docs": [], "compressed_summary": {}, "source_urls": []},
            }
            await entry(state)

        _, kwargs = mock_to_thread.call_args_list[0]
        assert kwargs.get("topic") == "news"
        assert kwargs.get("max_results") == 5

    @pytest.mark.asyncio
    async def test_deep_report_uses_advanced_depth(self):
        """deep_report template passes search_depth=advanced."""
        mock_search = MagicMock(return_value={"results": []})

        with (
            patch("agents.nodes.data_collector.TavilyClient") as mock_client_cls,
            patch("agents.nodes.data_collector.asyncio.to_thread") as mock_to_thread,
        ):
            mock_client_cls.return_value = MagicMock()
            mock_to_thread.return_value = mock_search()

            from agents.nodes.data_collector import entry

            state = {
                "base": {"user_input": "research", "template_name": "deep_report"},
                "collection": {"raw_docs": [], "compressed_summary": {}, "source_urls": []},
            }
            await entry(state)

        _, kwargs = mock_to_thread.call_args_list[0]
        assert kwargs.get("search_depth") == "advanced"
        assert kwargs.get("max_results") == 7
