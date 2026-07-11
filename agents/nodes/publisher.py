"""Publisher node — merge chapters, generate table of contents, output Markdown."""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Merge chapter drafts into final Markdown report with table of contents.

    Reads ``writing.chapter_drafts`` and ``writing.citation_list``,
    produces ``writing.final_content``.

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with final_content populated.
    """
    writing: dict[str, Any] = state.get("writing", {})
    base: dict[str, Any] = state.get("base", {})
    chapters: dict[str, str] = writing.get("chapter_drafts", {})
    citations: list[str] = writing.get("citation_list", [])

    # Build table of contents
    toc = "# 目录\n\n"
    for i, ch_name in enumerate(chapters.keys(), 1):
        toc += f"{i}. {ch_name}\n"

    # Merge chapters
    body_parts: list[str] = []
    for ch_name, content in chapters.items():
        body_parts.append(f"## {ch_name}\n\n{content}")

    # Build citation section
    citation_section = ""
    if citations:
        citation_section = "\n\n---\n\n## 引用来源\n\n"
        for i, cite in enumerate(citations, 1):
            citation_section += f"[{i}] {cite}\n"

    final = f"# 智能研报\n\n{toc}\n\n" + "\n\n".join(body_parts) + citation_section

    return {
        "writing": {
            "chapter_drafts": chapters,
            "final_content": final,
            "citation_list": citations,
        },
        "base": {**base, "status": "published"},
    }
