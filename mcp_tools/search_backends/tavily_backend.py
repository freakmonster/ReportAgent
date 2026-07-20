"""Tavily Search API backend — production search implementation."""

from __future__ import annotations

import logging
from typing import Any

from tavily import TavilyClient

from config.settings import settings

from .base import BaseSearchBackend

logger = logging.getLogger(__name__)


class TavilySearchBackend(BaseSearchBackend):
    """Search backend backed by the Tavily Search API (official SDK).

    Lazy-loads the TavilyClient singleton per AGENTS.md §5.2.
    Gracefully degrades with structured error results if API is unavailable.
    """

    _client: TavilyClient | None = None

    @classmethod
    def _get_client(cls) -> TavilyClient:
        """Lazy-initialize the TavilyClient singleton."""
        if cls._client is None:
            key = settings.tavily_api_key
            if not key:
                raise RuntimeError(
                    "TAVILY_API_KEY is not set. Configure it in environment "
                    "or config/environments/*.yaml."
                )
            cls._client = TavilyClient(api_key=key)
        return cls._client

    async def web_search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform web search via Tavily API."""
        try:
            client = self._get_client()
            import asyncio

            response = await asyncio.to_thread(
                client.search,
                query=query,
                search_depth=search_depth,
                max_results=min(max_results, 20),
                include_domains=kwargs.pop("include_domains", None),
                exclude_domains=kwargs.pop("exclude_domains", None),
            )
            return self._normalise_results(response.get("results", []))
        except RuntimeError:
            logger.warning("TavilySearchBackend: API key not configured")
            return []
        except Exception as exc:
            logger.warning(f"TavilySearchBackend.web_search failed: {exc}")
            return []

    async def news_search(
        self,
        query: str,
        max_results: int = 10,
        days: int = 7,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search recent news via Tavily API."""
        try:
            client = self._get_client()
            import asyncio

            response = await asyncio.to_thread(
                client.search,
                query=query,
                search_depth="advanced",
                max_results=min(max_results, 20),
                days=days,
                topic="news",
            )
            return self._normalise_results(response.get("results", []))
        except RuntimeError:
            logger.warning("TavilySearchBackend: API key not configured")
            return []
        except Exception as exc:
            logger.warning(f"TavilySearchBackend.news_search failed: {exc}")
            return []

    async def academic_search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search academic sources via Tavily API."""
        try:
            client = self._get_client()
            import asyncio

            response = await asyncio.to_thread(
                client.search,
                query=query,
                search_depth="advanced",
                max_results=min(max_results, 20),
                include_domains=[
                    "scholar.google.com",
                    "arxiv.org",
                    "semanticscholar.org",
                    "pubmed.ncbi.nlm.nih.gov",
                ],
            )
            return self._normalise_results(response.get("results", []))
        except RuntimeError:
            logger.warning("TavilySearchBackend: API key not configured")
            return []
        except Exception as exc:
            logger.warning(f"TavilySearchBackend.academic_search failed: {exc}")
            return []

    @property
    def name(self) -> str:
        return "tavily"

    @staticmethod
    def _normalise_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalise Tavily results to a consistent schema."""
        normalised: list[dict[str, Any]] = []
        for r in results:
            normalised.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0.0),
                }
            )
        return normalised
