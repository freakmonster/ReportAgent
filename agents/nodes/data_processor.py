"""Data Processor node — Map-Reduce summarization, ≤ 6K per chapter."""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Compress collected raw documents into per-chapter summaries.

    Input:  collection.raw_docs
    Output: collection.compressed_summary (Dict[chapter_name, summary ≤ 6000 chars])

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with compressed_summary populated.
    """
    collection: dict[str, Any] = state.get("collection", {})
    raw_docs: list[dict[str, str]] = collection.get("raw_docs", [])
    base: dict[str, Any] = state.get("base", {})

    if not raw_docs:
        return state

    # Group documents by topic (simple keyword matching)
    topics: dict[str, list[str]] = {
        "市场概况": [],
        "竞争格局": [],
        "政策环境": [],
        "技术趋势": [],
        "风险与展望": [],
    }

    for doc in raw_docs:
        content = doc.get("content", "")
        matched = False
        for topic in topics:
            if any(kw in content for kw in topic.replace("与", " ").split()):
                topics[topic].append(content[:2000])
                matched = True
                break
        if not matched:
            topics["市场概况"].append(content[:2000])

    # Compress each topic to ≤ 6K
    compressed: dict[str, str] = {}
    for topic, snippets in topics.items():
        combined = " ".join(snippets)
        compressed[topic] = combined[:6000]

    return {
        "collection": {
            "raw_docs": raw_docs,
            "compressed_summary": compressed,
            "source_urls": collection.get("source_urls", []),
        },
        "base": {**base, "status": "collecting"},
    }
