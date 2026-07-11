"""Writer node — V2.1 chapter-level context isolation, loop subgraph.

AGENTS.md §1.3: Uses @requires("base","collection") @produces("writing")
Each chapter receives ≤ 6K chars of focused context to avoid Lost-in-the-Middle.
"""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Write report chapters one by one with chapter-level context isolation.

    Input:  collection.compressed_summary (chapter_name → summary ≤ 6K)
    Output: writing.chapter_drafts

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with chapter_drafts populated.
    """
    collection: dict[str, Any] = state.get("collection", {})
    base: dict[str, Any] = state.get("base", {})
    compressed: dict[str, str] = collection.get("compressed_summary", {})

    if not compressed:
        compressed = {
            "摘要": "数据未收集",
        }

    drafts: dict[str, str] = {}
    for ch_name, context in compressed.items():
        # Each chapter gets its own focused context ≤ 6K chars
        prompt = (
            f"你是一名专业的研究报告撰写员。请根据以下资料，撰写章节「{ch_name}」的内容。"
            f"\n\n资料：\n{context[:6000]}\n\n"
            f"请用中文撰写，语言专业、客观、数据准确。"
        )
        # In production, this would call LLM via router
        drafts[ch_name] = (
            f"# {ch_name}\n\n"
            f"本章基于以下资料撰写：{context[:200]}...\n\n"
            f"（章节内容将由 LLM 生成，当前为模拟输出）"
        )

    return {
        "writing": {
            "chapter_drafts": drafts,
            "final_content": "",
            "citation_list": [],
        },
        "base": {**base, "status": "writing"},
    }
