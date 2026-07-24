"""Publisher node — merge chapters, generate table of contents, output Markdown."""

from __future__ import annotations

import asyncio
import re
import sys
from typing import Any


#  标题提取 
_TITLE_STRIP_PREFIXES = [
    r"^(?:请|帮我|帮我|请帮我|请为我)(?:分析|研究|撰写|生成|写一篇|写一份|总结|归纳|介绍|说明)",
    r"^(?:分析|研究|撰写|生成|总结|归纳|介绍|说明)",
    r"^(?:关于|有关|对于)",
]
_TITLE_STRIP_SUFFIXES = [
    r"(?:的分析|的研究|的分析报告|的研究报告|分析报告|研究报告|分析|研究|报告|的深度分析)$",
]


def _extract_title(user_input: str, max_len: int = 40) -> str:
    """从用户输入中提取报告标题。

    剥离常见的前缀动作词和后缀修饰词，保留核心主题。
    若处理结果为空或过长，回退为原文截断。
    """
    title = user_input.strip().strip("，。！？、,.")

    # 剥离前缀
    for pattern in _TITLE_STRIP_PREFIXES:
        title = re.sub(pattern, "", title)
        if title:
            break

    # 剥离后缀
    for pattern in _TITLE_STRIP_SUFFIXES:
        title = re.sub(pattern, "", title)

    title = title.strip().strip("，。！？、,.")

    # 回退：若剥离后为空，返回原文截断
    if not title:
        title = user_input.strip()[:max_len]
    elif len(title) > max_len:
        title = title[:max_len] + "..."

    return title


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
    template_name: str = base.get("template_name", "deep_report")
    user_input: str = base.get("user_input", "")

    # 动态标题（仅 deep_report 使用 H1 标题）
    report_title = _extract_title(user_input, max_len=34) + "的深度研报" if user_input else "智能研报"

    # Build citation section
    citation_section = ""
    if citations:
        citation_section = "\n\n---\n\n## 引用来源\n\n"
        for i, cite in enumerate(citations, 1):
            citation_section += f"- [{i}] {cite}\n"

    #  Extract charts for downstream rendering 
    collection: dict[str, Any] = state.get("collection", {})
    analysis: dict[str, Any] = collection.get("analysis", {})
    charts_data: list[dict[str, Any]] = analysis.get("charts", [])

    # Skip TOC and chapter headings for flash_news / earnings_analysis
    if template_name in ("flash_news", "earnings_analysis"):
        body_parts: list[str] = []
        for content in chapters.values():
            stripped = content.strip()
            # Strip "## chapter_title\n\n" prefix added by writer
            if stripped.startswith("## "):
                stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
            body_parts.append(stripped.strip())
        final = "\n\n".join(body_parts) + citation_section + "\n"
    else:
        # Build table of contents
        toc = "# 目录\n\n"
        for i, ch_name in enumerate(chapters.keys(), 1):
            toc += f"{i}. {ch_name}\n"

        # Merge chapters (content already starts with ## chapter_name from writer)
        body_parts = []
        for ch_name, content in chapters.items():
            body_parts.append(content.strip())

        final = f"# {report_title}\n\n{toc}\n\n" + "\n\n".join(body_parts) + citation_section + "\n"

    # 异步写入短期记忆
    session_id = base.get("session_id", "")
    if session_id:
        user_id = base.get("user_id", "anonymous")
        asyncio.create_task(
            _save_short_term_memory(
                user_id,
                session_id,
                query=base.get("user_input", ""),
                summary=final[:300] if final else "",
                template=base.get("template_name", "deep_report"),
                model=base.get("model", "deepseek-flash"),
                workflow_id=base.get("workflow_id", ""),
            )
        )

    return {
        "writing": {
            "chapter_drafts": chapters,
            "final_content": final,
            "citation_list": citations,
            "charts": charts_data,
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

        await save_memory(
            user_id,
            session_id,
            {
                "query": query,
                "summary": summary,
                "template": template,
                "model": model,
                "workflow_id": workflow_id,
            },
        )
        print(
            f"[publisher] short-term memory saved | session={session_id}",
            file=sys.stderr,
            flush=True,
        )
    except Exception as e:
        print(f"[publisher] short-term memory save failed: {e}", file=sys.stderr, flush=True)
