"""Publisher node — merge chapters, generate table of contents, output Markdown."""

from __future__ import annotations

import asyncio
import sys
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

    # Merge chapters (content already starts with ## chapter_name from writer)
    body_parts: list[str] = []
    for ch_name, content in chapters.items():
        body_parts.append(content.strip())

    # Build citation section
    citation_section = ""
    if citations:
        citation_section = "\n\n---\n\n## 引用来源\n\n"
        for i, cite in enumerate(citations, 1):
            citation_section += f"- [{i}] {cite}\n"

    final = f"# 智能研报\n\n{toc}\n\n" + "\n\n".join(body_parts) + citation_section + "\n"

    # 异步写入短期记忆
    session_id = base.get("session_id", "")
    if session_id:
        user_id = base.get("user_id", "anonymous")
        asyncio.create_task(_save_short_term_memory(
            user_id, session_id,
            query=base.get("user_input", ""),
            summary=final[:300] if final else "",
            template=base.get("template_name", "deep_report"),
            model=base.get("model", "deepseek-flash"),
            workflow_id=base.get("workflow_id", ""),
        ))

    return {
        "writing": {
            "chapter_drafts": chapters,
            "final_content": final,
            "citation_list": citations,
        },
        "base": {**base, "status": "published"},
    }


async def _save_short_term_memory(
    user_id: str,
    session_id: str,
    query: str,
    summary: str,
    template: str,
    model: str,
    workflow_id: str,
) -> None:
    """Persist a summary snapshot to Redis short-term memory for this session."""
    try:
        from infrastructure.memory.short_term import save_memory
        await save_memory(user_id, session_id, {
            "query": query,
            "summary": summary,
            "template": template,
            "model": model,
            "workflow_id": workflow_id,
        })
        print(f"[publisher] short-term memory saved | session={session_id}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[publisher] short-term memory save failed: {e}", file=sys.stderr, flush=True)
