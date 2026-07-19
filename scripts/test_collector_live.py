"""Smoke test: data_collector returns real web content (not hardcoded)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

from agents.nodes.data_collector import entry


async def test():
    state = {
        "base": {"user_input": "新能源汽车", "template_name": "flash_news"},
        "collection": {"raw_docs": [], "compressed_summary": {}, "source_urls": []},
    }
    result = await entry(state)
    docs = result["collection"]["raw_docs"]
    print(f"Docs collected: {len(docs)}")
    for i, d in enumerate(docs, 1):
        t = d["title"][:60]
        u = d["url"][:70]
        c = len(d["content"])
        print(f"  [{i}] {t}")
        print(f"      URL: {u}")
        print(f"      Content: {c} chars")
    no_fake = "example.com" not in str(docs)
    print(f"Real data (no example.com): {no_fake}")
    assert no_fake, "Still using hardcoded example.com data!"

asyncio.run(test())
