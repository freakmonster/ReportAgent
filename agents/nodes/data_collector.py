"""Data Collector node — parallel MCP calls with circuit breaker protection."""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Collect data from internal sources (simulated MCP search + retrieval).

    In production, this node would:
    - Call MCP search server (Tavily) for web results
    - Call vector store (Qdrant) for relevant pre-indexed documents
    - Handle circuit breaker degradation to internal tools

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with collection.raw_docs and collection.source_urls.
    """
    base: dict[str, Any] = state.get("base", {})
    collection: dict[str, Any] = state.get("collection", {})

    # ── Simulated data collection ─────────────────────────────────────
    # In production, this would be real MCP + Qdrant calls
    raw_docs: list[dict[str, str]] = [
        {
            "title": "2026年新能源汽车市场分析",
            "url": "https://example.com/report1",
            "content": "2026年上半年新能源汽车销量突破500万辆，同比增长35%，市场渗透率达到42%。",
        },
        {
            "title": "动力电池技术发展",
            "url": "https://example.com/report2",
            "content": "固态电池技术取得突破，能量密度达到500Wh/kg，预计2027年量产。",
        },
        {
            "title": "新能源汽车政策汇总",
            "url": "https://example.com/report3",
            "content": "国务院发布新能源汽车产业发展规划，2026-2030年目标渗透率60%。",
        },
    ]
    source_urls = [doc["url"] for doc in raw_docs]

    return {
        "collection": {
            "raw_docs": raw_docs,
            "compressed_summary": collection.get("compressed_summary", {}),
            "source_urls": source_urls,
        },
        "base": {**base, "status": "collecting"},
    }
