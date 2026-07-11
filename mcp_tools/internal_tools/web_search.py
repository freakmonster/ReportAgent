"""
Internal web search tool — Fallback for MCP search degradation.

Used when the MCP search server circuit breaker is OPEN or when
the search server is unreachable. Provides a lightweight search
implementation that can use multiple backends.

Default backend: DuckDuckGo (no API key required) if available,
otherwise returns a structured fallback response.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Perform a web search via available fallback backends.

    Attempts in order:
    1. duckduckgo-search library (if installed)
    2. Plain httpx scrape of DuckDuckGo HTML (fallback)
    3. Return informative empty result set

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of result dicts with keys: title, url, snippet.
    """
    logger.info("Internal web search for: %s (max=%d)", query, max_results)

    # Option 1: duckduckgo-search library
    try:
        from duckduckgo_search import DDGS
        results: list[dict[str, Any]] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        if results:
            logger.info("Internal search returned %d results via duckduckgo-search", len(results))
            return results
    except ImportError:
        logger.debug("duckduckgo-search not installed, trying next fallback")
    except Exception as exc:
        logger.warning("duckduckgo-search failed: %s", exc)

    # Option 2: Direct DuckDuckGo HTML (minimal, no external lib)
    try:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "ResearchAgent/1.0"},
            )
            if response.status_code == 200:
                # Basic HTML parsing
                results = _parse_ddg_html(response.text, max_results)
                if results:
                    logger.info("Internal search returned %d results via DDG HTML", len(results))
                    return results
    except ImportError:
        logger.debug("httpx not available for DDG HTML fallback")
    except Exception as exc:
        logger.warning("DDG HTML fallback failed: %s", exc)

    # Option 3: Informative empty result
    logger.warning("All internal search backends failed for query: %s", query)
    return [
        {
            "title": f"Search: {query}",
            "url": "",
            "snippet": (
                "Internal search is currently unavailable. Please try again "
                "later or refine your query. The MCP search service may be "
                "experiencing issues (circuit breaker OPEN)."
            ),
        }
    ]


def _parse_ddg_html(html: str, max_results: int) -> list[dict[str, Any]]:
    """Basic HTML parser for DuckDuckGo HTML results page.

    Uses regex to extract title, URL, and snippet from result blocks.
    This is a lightweight fallback; for production use, prefer the
    duckduckgo-search library or BeautifulSoup.
    """
    import re

    results: list[dict[str, Any]] = []
    # Match result blocks in DDG HTML
    result_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    matches = result_pattern.findall(html)
    for url, title_raw, snippet_raw in matches[:max_results]:
        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet_raw).strip()
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


async def news_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search for news articles (internal fallback)."""
    # Append "news" to query to bias results
    return await web_search(f"{query} news", max_results=max_results)


async def academic_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search for academic papers (internal fallback)."""
    # Append "research paper" to bias results
    return await web_search(f"{query} research paper", max_results=max_results)


# ---------------------------------------------------------------------------
# Callable tool interface (compatible with registry)
# ---------------------------------------------------------------------------

async def web_search_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    """Registry-compatible callable for web_search.

    Args:
        arguments: {"query": str, "max_results": int | None}

    Returns:
        Dict with key "results" containing the search results.
    """
    query = arguments.get("query", "")
    max_results = int(arguments.get("max_results", 5))
    results = await web_search(query, max_results=max_results)
    return {"results": results, "query": query, "source": "internal", "timestamp": datetime.utcnow().isoformat()}


async def news_search_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    """Registry-compatible callable for news_search."""
    query = arguments.get("query", "")
    max_results = int(arguments.get("max_results", 5))
    results = await news_search(query, max_results=max_results)
    return {"results": results, "query": query, "source": "internal_news", "timestamp": datetime.utcnow().isoformat()}
