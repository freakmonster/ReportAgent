"""Search backend strategy abstraction.

AGENTS.md §6.1 compliant: Strategy pattern with YAML-configurable backends.

Backends:
- ``tavily`` — Tavily Search API (default, via official SDK)
- ``mock``   — Deterministic mock for development/testing
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSearchBackend(ABC):
    """Abstract search backend interface.

    All search backends must implement this interface, allowing
    runtime switching via YAML config (``search_backend`` key).

    Supports three search modes matching the MCP Search Server contract:
    - web_search
    - news_search
    - academic_search
    """

    @abstractmethod
    async def web_search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform a general web search.

        Args:
            query: Search query string.
            max_results: Maximum number of results (1-20).
            search_depth: ``"basic"`` or ``"advanced"``.

        Returns:
            List of result dicts with keys: title, url, content, score.
        """
        ...

    @abstractmethod
    async def news_search(
        self,
        query: str,
        max_results: int = 10,
        days: int = 7,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search recent news articles.

        Args:
            query: Search query.
            max_results: Maximum number of results (1-20).
            days: Lookback window in days (1-365).

        Returns:
            List of news result dicts.
        """
        ...

    @abstractmethod
    async def academic_search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search academic/scholarly sources.

        Args:
            query: Search query.
            max_results: Maximum number of results.

        Returns:
            List of academic result dicts.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable backend name for logging/metrics."""
        return self.__class__.__name__
