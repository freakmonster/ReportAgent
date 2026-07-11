"""
Search MCP Server — Tavily API bridge.

Provides web search, news search, and academic search capabilities
via the Tavily Search API. Runs as an independent HTTP (FastAPI) service.

Environment: TAVILY_API_KEY must be set.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tavily API client (lazy-initialized)
# ---------------------------------------------------------------------------

class TavilySearchClient:
    """Async wrapper around the Tavily Search API."""

    BASE_URL: str = "https://api.tavily.com"

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._http_client: object | None = None

    def _get_api_key(self) -> str:
        """Resolve the Tavily API key from settings."""
        if self._api_key is None:
            from config.settings import settings

            self._api_key = settings.tavily_api_key
            if not self._api_key:
                raise TavilyConfigError(
                    "TAVILY_API_KEY is not set. Please set it in your "
                    "environment variables or config YAML."
                )
        return self._api_key

    async def _client(self) -> object:
        """Lazy-init httpx AsyncClient."""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=httpx.Timeout(60.0),
            )
        return self._http_client

    async def search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Perform a general web search via Tavily.

        Args:
            query: Search query string.
            search_depth: "basic" or "advanced".
            max_results: Maximum number of results (1-20).
            include_domains: Optional list of domains to include.
            exclude_domains: Optional list of domains to exclude.

        Returns:
            Search results dict with keys: results, response_time, query.
        """
        client = await self._client()
        import httpx

        payload: dict[str, Any] = {
            "api_key": self._get_api_key(),
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        try:
            response = await client.post("/search", json=payload)  # type: ignore[union-attr]
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Tavily API HTTP %d: %s", exc.response.status_code, exc.response.text[:300])
            raise TavilyAPIError(
                f"Tavily API returned {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Tavily API request failed: %s", exc)
            raise TavilyAPIError(f"Tavily API request failed: {exc}") from exc

    async def news_search(
        self,
        query: str,
        days: int = 7,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Search for recent news articles.

        Args:
            query: Search query string.
            days: Number of days back to search (1-365).
            max_results: Maximum number of results.

        Returns:
            News search results.
        """
        client = await self._client()
        import httpx

        payload: dict[str, Any] = {
            "api_key": self._get_api_key(),
            "query": query,
            "topic": "news",
            "days": days,
            "max_results": max_results,
        }

        try:
            response = await client.post("/search", json=payload)  # type: ignore[union-attr]
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Tavily news search HTTP %d", exc.response.status_code)
            raise TavilyAPIError(f"Tavily news search failed: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("Tavily news search request failed: %s", exc)
            raise TavilyAPIError(f"Tavily news search request failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()  # type: ignore[union-attr]
            self._http_client = None


# ---------------------------------------------------------------------------
# Pydantic request models (module-level for FastAPI 0.115+ compat)
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    search_depth: str = Field(default="basic", description="basic or advanced")
    max_results: int = Field(default=10, ge=1, le=20)
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None


class NewsSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    days: int = Field(default=7, ge=1, le=365)
    max_results: int = Field(default=10, ge=1, le=20)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

def create_search_app() -> object:
    """Create and configure the FastAPI search MCP server application."""
    from fastapi import FastAPI, HTTPException

    app = FastAPI(title="MCP Search Server", version="0.1.0")
    tavily = TavilySearchClient()

    # ── Health ──────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "mcp-search"}

    # ── Tool endpoints ──────────────────────────────────────────────

    @app.post("/tools/web_search")
    async def web_search(req: SearchRequest) -> dict[str, Any]:
        """General web search."""
        try:
            return await tavily.search(
                query=req.query,
                search_depth=req.search_depth,
                max_results=req.max_results,
                include_domains=req.include_domains,
                exclude_domains=req.exclude_domains,
            )
        except TavilyAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/news_search")
    async def news_search(req: NewsSearchRequest) -> dict[str, Any]:
        """News-specific search."""
        try:
            return await tavily.news_search(
                query=req.query,
                days=req.days,
                max_results=req.max_results,
            )
        except TavilyAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/academic_search")
    async def academic_search(req: SearchRequest) -> dict[str, Any]:
        """Academic/scholarly search (uses general search with include_domains)."""
        academic_domains = req.include_domains or [
            "scholar.google.com",
            "arxiv.org",
            "semanticscholar.org",
            "researchgate.net",
        ]
        try:
            return await tavily.search(
                query=req.query,
                search_depth="advanced",
                max_results=req.max_results,
                include_domains=academic_domains,
            )
        except TavilyAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_search_app()


def main() -> None:
    """Run the search MCP server."""
    import uvicorn
    from config.settings import settings

    uvicorn.run(
        "mcp_tools.mcp_servers.search_server:app",
        host="0.0.0.0",
        port=8001,
        log_level=settings.log_level.lower(),
    )


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class TavilyAPIError(Exception):
    """Raised when the Tavily API call fails."""


class TavilyConfigError(Exception):
    """Raised when Tavily is not properly configured."""
