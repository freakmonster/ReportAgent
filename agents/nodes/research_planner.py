"""Research Planner node — decompose user query into structured chapter task list.

Outputs a list of chapter topics for the report.
"""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Plan the research chapters based on user intent and template.

    Reads: base.template_name, base.user_input
    Sets:  collection.chapter_plan

    Args:
        state: Current ReportState.

    Returns:
        Partial state update.
    """
    base: dict[str, Any] = state.get("base", {})
    template_name = base.get("template_name", "deep_report")

    # Template-based chapter planning
    plans: dict[str, list[str]] = {
        "deep_report": [
            "摘要与概述",
            "市场规模分析",
            "竞争格局",
            "政策环境",
            "技术趋势",
            "重点企业分析",
            "风险提示",
            "投资建议",
            "结论与展望",
        ],
        "flash_news": [
            "核心要点",
            "关键数据",
            "市场反应",
        ],
        "earnings_analysis": [
            "公司概况",
            "收入分析",
            "利润分析",
            "现金流分析",
            "资产负债分析",
            "风险提示",
            "投资评级与展望",
        ],
    }

    chapters = plans.get(template_name, plans["deep_report"])

    return {
        "base": base,
        "collection": {
            "raw_docs": [],
            "compressed_summary": {},
            "source_urls": [],
            "chapter_plan": chapters,
        },
    }
