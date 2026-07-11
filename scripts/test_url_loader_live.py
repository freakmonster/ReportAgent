"""Real-world smoke test for url_loader — fetches actual web pages.

Usage:
    python scripts/test_url_loader_live.py
"""

import asyncio

import httpx
from retrieval.loaders.url_loader import fetch_multiple, fetch_url, WebPage


# ── Known stable URLs for quick verification ──────────────────────────

# ── Stable URLs (many sites block non-browser User-Agents) ──────────

STABLE_URLS: list[str] = [
    "https://www.example.com",                 # always up, allows any User-Agent
]


async def test_fixed_urls() -> list[WebPage]:
    """Fetch a set of known stable URLs and report results."""
    pages: list[WebPage] = []
    for url in STABLE_URLS:
        try:
            page = await fetch_url(url, timeout=15, max_length=10_000)
            pages.append(page)
            print(f"[fixed] \u2705 {url}")
            print(f"        Title: {page.title}")
            print(f"        Length: {page.char_count} chars")
            print()
        except Exception as exc:
            print(f"[fixed] \u274c {url}  ->  {exc}")
            print()
    return pages


async def test_search_then_fetch() -> list[WebPage]:
    """Search Tavily for real articles, then fetch their content.

    Requires TAVILY_API_KEY in EnvConfig.md or environment.
    """
    from pathlib import Path

    # Read TAVILY_API_KEY from EnvConfig.md
    env_path = Path(__file__).resolve().parent.parent / "EnvConfig.md"
    api_key = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("| `TAVILY_API_KEY` |"):
                parts = [p.strip() for p in line.split("|")]
                # Format: | label | key_value | source_url |
                #         [0]"" [1]"TAVILY_API_KEY" [2]"tvly-dev-..." [3]"https://tavily.com ..."
                if len(parts) >= 3:
                    api_key = parts[2].strip("`").strip()
                    break

    if not api_key:
        print("[search] \u274c TAVILY_API_KEY not found in EnvConfig.md, skipping live search")
        return []

    # Search via Tavily
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as c:
            r = await c.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": "2026年新能源汽车 市场分析",
                    "search_depth": "advanced",
                    "max_results": 5,
                },
            )
            if r.status_code in (401, 403):
                print(f"[search] \u274c Tavily API key expired or invalid (HTTP {r.status_code})")
                print("[search]     Please update the key in EnvConfig.md")
                print(f"[search]     Current key: {api_key[:12]}...")
                return []
            r.raise_for_status()
            results = r.json().get("results", [])
            urls = [
                item["url"] for item in results
                if item.get("url") and not item["url"].lower().endswith(".pdf")
            ]
    except httpx.HTTPStatusError:
        print(f"[search] \u274c Tavily HTTP error, skipping live search")
        return []
    except Exception as exc:
        print(f"[search] \u274c Tavily request failed: {exc}")
        return []

    if not urls:
        print("[search] \u26a0\ufe0f  No search results returned")
        return []

    print(f"[search] \u231b  Found {len(urls)} URLs, fetching content...\n")

    pages = await fetch_multiple(urls, timeout=30, max_length=50_000, max_concurrent=3)

    for page in pages:
        print(f"[search] \u2705 {page.url}")
        print(f"        Title: {page.title}")
        print(f"        Length: {page.char_count} chars")
        preview = page.text[:200].replace("\n", " ")
        print(f"        Preview: {preview}...")
        print()

    failed = len(urls) - len(pages)
    if failed:
        print(f"[search] \u274c {failed}/{len(urls)} URLs failed to fetch")
    return pages


# ── Main ─────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 65)
    print("  url_loader \u5b9e\u9645\u722c\u53d6\u6d4b\u8bd5  (Live Smoke Test)")
    print("=" * 65)
    print()

    # Phase 1: fixed stable URLs
    print("--- Phase 1: Stable URLs ---")
    fixed_pages = await test_fixed_urls()

    # Phase 2: search + fetch real articles
    print("--- Phase 2: Tavily Search + Fetch ---")
    search_pages = await test_search_then_fetch()

    # Summary
    total = len(fixed_pages) + len(search_pages)
    print("=" * 65)
    if total:
        avg_len = sum(p.char_count for p in fixed_pages + search_pages) / total
        print(f"  Total: {total} pages fetched successfully")
        print(f"  Average content length: {avg_len:,.0f} chars")
    else:
        print("  \u26a0\ufe0f  No pages fetched (check API key and network)")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
