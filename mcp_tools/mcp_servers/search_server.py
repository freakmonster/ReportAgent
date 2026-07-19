"""
Search MCP Server — Tavily API bridge using official SDK.

Provides web search, news search, and academic search capabilities
via the Tavily Search API. Runs as an independent HTTP (FastAPI) service.

Environment: TAVILY_API_KEY must be set.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field
from tavily import TavilyClient

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tavily API client factory (lazy-initialized)
# ---------------------------------------------------------------------------

def _get_tavily_client() -> TavilyClient:
    """Return a lazily-initialized TavilyClient singleton.

    The SDK client is NOT created at module import time (per AGENTS.md ~5.2).
    """
    global _tavily_client
    if _tavily_client is None:
        key = settings.tavily_api_key
        if not key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set. Please set it in environment "
                "variables or config YAML."
            )
        _tavily_client = TavilyClient(api_key=key)
    return _tavily_client


_tavily_client: TavilyClient | None = None


# ---------------------------------------------------------------------------
# Pydantic request models
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

    # ── Health ──────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "mcp-search"}

    # ── Tool endpoints ──────────────────────────────────────────────

    @app.post("/tools/web_search")
    async def web_search(req: SearchRequest) -> dict[str, Any]:
        """General web search via Tavily SDK."""
        try:
            client = _get_tavily_client()
            return await asyncio.to_thread(
                client.search,
                query=req.query,
                search_depth=req.search_depth,
                max_results=req.max_results,
                include_domains=req.include_domains,
                exclude_domains=req.exclude_domains,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/news_search")
    async def news_search(req: NewsSearchRequest) -> dict[str, Any]:
        """News-specific search via Tavily SDK."""
        try:
            client = _get_tavily_client()
            return await asyncio.to_thread(
                client.search,
                query=req.query,
                topic="news",
                days=req.days,
                max_results=req.max_results,
            )
        except Exception as exc:
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
            client = _get_tavily_client()
            return await asyncio.to_thread(
                client.search,
                query=req.query,
                search_depth="advanced",
                max_results=req.max_results,
                include_domains=academic_domains,
            )
        except Exception as exc:
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
