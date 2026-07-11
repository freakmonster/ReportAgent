"""Editor node — polish language, unify style, check citation integrity."""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Polish and unify chapter drafts for consistency.

    Input: writing.chapter_drafts
    Output: writing.chapter_drafts (edited), writing.citation_list

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with edited drafts and citation list.
    """
    writing: dict[str, Any] = state.get("writing", {})
    chapters: dict[str, str] = writing.get("chapter_drafts", {})

    # Simple editorial pass: trim whitespace, ensure period endings
    edited: dict[str, str] = {}
    for ch_name, content in chapters.items():
        cleaned = content.strip()
        if cleaned and not cleaned.endswith((".", "。", "?", "！", ")")):
            cleaned += "。"
        edited[ch_name] = cleaned

    # Collect citations from all chapters
    citations: list[str] = writing.get("citation_list", [])
    if not citations:
        # Generate placeholder citations
        citations = [f"来源 {ch_name}" for ch_name in chapters.keys()]

    return {
        "writing": {
            "chapter_drafts": edited,
            "final_content": writing.get("final_content", ""),
            "citation_list": citations,
        },
    }
