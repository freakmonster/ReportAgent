"""Live integration test for Tavily Extract API using the official SDK.

Usage:
    python scripts/test_tavily_extract.py

Requires: TAVILY_API_KEY env var or set in config.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tavily import TavilyClient

from config.settings import settings


def main():
    key = settings.tavily_api_key
    if not key:
        print("[FAIL] TAVILY_API_KEY not set. Run: $env:TAVILY_API_KEY = 'tvly-dev-...'")
        return

    client = TavilyClient(api_key=key)

    urls = [
        #"https://sichuan.scol.com.cn/ggxw/202511/83161448.html",
        "https://china.jdpower.com/zh-hans/press-releases/2026zhongguoxinnengyuanqichechanpinmeilizhishuyanjiu",
        #"https://www.cada.cn/Trends/info_91_10496.html",
    ]

    # ── 1. Basic extract ────────────────────────────────────────────
    print("=" * 60)
    print("  1. Basic Extract (format=markdown)")
    print("=" * 60)
    t0 = time.time()
    response = client.extract(urls=urls, extract_depth="basic", format="markdown")
    elapsed = time.time() - t0

    print(f"  Response time: {elapsed:.2f}s")
    print(f"  Request ID: {response.get('request_id', 'N/A')}")

    results = response.get("results", [])
    failed = response.get("failed_results", [])
    print(f"  Success: {len(results)}, Failed: {len(failed)}")
    print()

    for i, r in enumerate(results, 1):
        content = r.get("raw_content", "")
        print(f"  [{i}] {r['url'][:70]}")
        print(f"      Content length: {len(content)} chars")
        # Show first 200 chars of content
        preview = content[:].replace("\n", " ").replace("  ", " ")
        print(f"      Preview: {preview}...")
        print()

    if failed:
        print("  Failed URLs:")
        for f in failed:
            print(f"    - {f['url'][:60]}: {f['error']}")
        print()

    # ── 2. Advanced extract with query reranking ────────────────────
    print("=" * 60)
    print("  2. Advanced Extract (query reranking)")
    print("=" * 60)
    t0 = time.time()
    response = client.extract(
        urls=urls[:2],
        extract_depth="advanced",
        format="markdown",
        query="新能源汽车 销量 渗透率",
        chunks_per_source=3,
    )
    elapsed = time.time() - t0

    print(f"  Response time: {elapsed:.2f}s")
    print(f"  Success: {len(response.get('results', []))}, Failed: {len(response.get('failed_results', []))}")
    print()

    for i, r in enumerate(response.get("results", []), 1):
        content = r.get("raw_content", "")
        # Count chunk markers
        chunk_count = content.count("<chunk ") or content.count("[...]")
        print(f"  [{i}] {len(content)} chars, ~{chunk_count} chunks")
        preview = content[:150].replace("\n", " ").replace("  ", " ")
        print(f"      {preview}...")
        print()

    # ── 3. Plain text extract ───────────────────────────────────────
    print("=" * 60)
    print("  3. Text Extract (format=text)")
    print("=" * 60)
    t0 = time.time()
    response = client.extract(urls=urls[:1], extract_depth="basic", format="text")
    elapsed = time.time() - t0

    r = response.get("results", [{}])[0]
    print(f"  Response time: {elapsed:.2f}s")
    print(f"  Content length: {len(r.get('raw_content', ''))} chars (text mode)")
    print()

    print("  All 3 extract modes tested successfully.")


if __name__ == "__main__":
    main()
