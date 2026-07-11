"""Data Analyst node — analyze data, draw conclusions, generate charts."""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze collected data and append analytical conclusions.

    Input:  collection.raw_docs
    Output: collection with enriched data

    Args:
        state: Current ReportState.

    Returns:
        Partial state update.
    """
    collection: dict[str, Any] = state.get("collection", {})
    raw_docs: list[dict[str, str]] = collection.get("raw_docs", [])
    base: dict[str, Any] = state.get("base", {})

    # Extract data points for chart generation
    analysis = {
        "doc_count": len(raw_docs),
        "total_chars": sum(len(d.get("content", "")) for d in raw_docs),
        "sources": collection.get("source_urls", []),
    }

    return {
        "collection": {
            "raw_docs": raw_docs,
            "compressed_summary": collection.get("compressed_summary", {}),
            "source_urls": collection.get("source_urls", []),
            "analysis": analysis,
        },
        "base": {**base, "status": "analyzing"},
    }
