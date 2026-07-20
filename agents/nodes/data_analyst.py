"""Data Analyst node — analyze data, draw conclusions, generate charts.

Responsibilities:
1. Extract key metrics from raw_docs (numbers, percentages, units)
2. Call DeepSeek LLM to generate data trend insights (Phase 3)
3. Call MCP Chart Server for visualization when chartable data exists (Phase 4)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Error prefixes for propagating failure info in results
_INSIGHTS_ERROR_PREFIX = "__INSIGHTS_ERR__:"
_CHARTS_ERROR_PREFIX = "__CHARTS_ERR__:"


async def _generate_insights(
    analysis: dict[str, Any], model: str = "deepseek-flash", max_retries: int = 2
) -> list[str]:
    """Call LLM to generate data trend insights.

    Retries once on empty/unparseable output, then falls back to empty list.

    Args:
        analysis: Dict with doc_count, total_chars, data_quality, key_metrics.
        model: LLM model string (deepseek-flash, qwen-max, etc.).
        max_retries: Maximum LLM call attempts (default 2).

    Returns:
        List of insight strings (up to 5).
    """
    if not analysis.get("key_metrics"):
        return []
    try:
        from models.llm_providers.resolver import resolve_llm_client
        from models.prompts.prompt_manager import get_prompt_manager

        pm = get_prompt_manager()
        prompt = pm.render(
            "data_analyst_insights",
            doc_count=analysis.get("doc_count", 0),
            total_chars=analysis.get("total_chars", 0),
            data_quality=analysis.get("data_quality", "unknown"),
            key_metrics=", ".join(analysis.get("key_metrics", [])[:20]),
        )

        client = resolve_llm_client(model)
        for attempt in range(max_retries):
            response = await client.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请生成数据洞察"},
                ],
                temperature=0.2 + attempt * 0.1,  # slightly more variance on retry
                max_tokens=500,
            )

            content: str = response["choices"][0]["message"]["content"]
            content = content.strip()
            logger.debug("LLM raw response (attempt %d): %r", attempt + 1, content[:300])

            # Try to parse as JSON array
            if content.startswith("["):
                import json

                try:
                    insights = json.loads(content)
                    if insights:
                        return [str(i) for i in insights[:5]]
                    # Empty JSON array "[]" — retry
                except json.JSONDecodeError:
                    # JSON parse failed — retry
                    pass
            elif not content:
                # Empty response — retry
                pass
            else:
                # Non-JSON content — try line-splitting
                raw_lines = content.split("\n")
                lines = []
                for line in raw_lines:
                    line = line.strip(" \t\"'[]{}").strip()
                    line = line.lstrip("- ").strip()
                    line = line.rstrip(",;").strip()
                    if line and len(line) > 3:
                        lines.append(line)
                if lines:
                    return lines[:5]

            if attempt < max_retries - 1:
                logger.info(
                    "LLM insights retry %d/%d — output was empty or unparseable",
                    attempt + 1,
                    max_retries - 1,
                )

        # All retries exhausted — return empty for caller to handle fallback
        return []
    except Exception as exc:
        logger.warning("LLM insights generation failed: %s", exc, exc_info=True)
        return [_INSIGHTS_ERROR_PREFIX + str(exc)]


async def _generate_charts(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect chartable data and call MCP Chart Server.

    Falls back to empty list on any failure.

    Args:
        analysis: Dict with key_metrics and doc_count.

    Returns:
        List of chart entry dicts (may be empty).
    """
    metrics: list[str] = analysis.get("key_metrics", [])
    if not metrics or analysis.get("doc_count", 0) < 2:
        return []

    try:
        import httpx

        from config.settings import settings

        # Extract numeric values for charting
        numbers: list[tuple[str, float]] = []
        for m in metrics:
            match = re.search(r"([\d.]+)", m)
            if match:
                val = float(match.group(1))
                # Normalize: if value has 亿/万 suffix
                if "亿" in m:
                    val *= 10000  # convert to wan-equivalent
                numbers.append((m, val))

        if len(numbers) < 2:
            return []

        numbers = numbers[:8]  # top 8 for readability
        labels = [n[0][:15] for n in numbers]
        values = [n[1] for n in numbers]

        url = f"{settings.mcp_chart_url.rstrip('/')}/tools/generate_bar_chart"
        body = {
            "title": "Key Metrics Overview",
            "x_label": "Metrics",
            "y_label": "Value",
            "data": {"Metrics": values},
            "x_ticks": labels,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            data = response.json()

        if data:
            chart_entry: dict[str, Any] = {
                "chart_type": data.get("chart_type", "bar"),
                "title": "Key Metrics Overview",
                "image_base64": data.get("image_base64", ""),
            }
            return [chart_entry] if chart_entry["image_base64"] else []
        return []
    except Exception as exc:
        logger.warning("MCP chart generation failed: %s", exc, exc_info=True)
        return [_CHARTS_ERROR_PREFIX + str(exc)]


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze collected data and append analytical conclusions.

    Input:  collection.raw_docs, collection.source_urls
    Output: collection with enriched analysis dict

    Steps:
    1. Extract key metrics via regex from all raw docs
    2. Determine data quality level
    3. Call _generate_insights() for LLM-driven trend analysis
    4. Call _generate_charts() for MCP chart generation

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with analysis dict populated.
    """
    collection: dict[str, Any] = state.get("collection", {})
    raw_docs: list[dict[str, str]] = collection.get("raw_docs", [])
    base: dict[str, Any] = state.get("base", {})

    # 1. Extract key metrics from all docs
    pattern: str = r"\d+\.?\d*\s*%|\d+(?:\.\d+)?\s*(?:亿|万|美元|万元|亿元|%)"
    all_metrics: list[str] = []
    for doc in raw_docs:
        matches = re.findall(pattern, doc.get("content", ""))
        all_metrics.extend(matches)
    # Deduplicate and limit to top 30
    key_metrics = list(dict.fromkeys(all_metrics))[:30]

    # 2. Determine data quality
    doc_count = len(raw_docs)
    total_chars = sum(len(d.get("content", "")) for d in raw_docs)
    if doc_count >= 5:
        data_quality = "good"
    elif doc_count >= 2:
        data_quality = "fair"
    else:
        data_quality = "poor"

    # 3. Build analysis dict
    analysis: dict[str, Any] = {
        "doc_count": doc_count,
        "total_chars": total_chars,
        "key_metrics": key_metrics,
        "data_quality": data_quality,
        "insights": [],
        "charts": [],
    }

    # 4. Generate LLM insights (Phase 3)
    if analysis.get("key_metrics"):
        model: str = base.get("model", "deepseek-flash")
        insights_result = await _generate_insights(analysis.copy(), model=model)
        analysis["insights"] = [
            i for i in insights_result if not i.startswith(_INSIGHTS_ERROR_PREFIX)
        ]
        error_msgs = [
            i[len(_INSIGHTS_ERROR_PREFIX) :]
            for i in insights_result
            if i.startswith(_INSIGHTS_ERROR_PREFIX)
        ]
        if error_msgs:
            analysis["_insights_error"] = error_msgs[0]

        # If LLM returned empty with no error, generate smart template-based fallback
        if not analysis["insights"] and not error_msgs and key_metrics:
            # Extract pure numbers for statistical summary
            import math

            pure_nums: list[float] = []
            for m in key_metrics:
                match = re.search(r"([\d.]+)", m)
                if match:
                    pure_nums.append(float(match.group(1)))
            parts = [f"共分析{doc_count}篇文档，提取{len(key_metrics)}项关键指标"]
            if pure_nums:
                parts.append(f"数值范围[{min(pure_nums):.1f}, {max(pure_nums):.1f}]")
                if len(pure_nums) >= 3:
                    avg = sum(pure_nums) / len(pure_nums)
                    parts.append(
                        f"均值{avg:.1f}，中位数{sorted(pure_nums)[len(pure_nums) // 2]:.1f}"
                    )
            parts.append(f"涵盖{'、'.join(key_metrics[:5])}等")
            analysis["insights"] = ["；".join(parts)]

    # 5. Generate MCP charts (Phase 4)
    charts_result = await _generate_charts(analysis.copy())
    analysis["charts"] = [
        c for c in charts_result if not isinstance(c, str) or not c.startswith(_CHARTS_ERROR_PREFIX)
    ]
    error_msgs = [
        c[len(_CHARTS_ERROR_PREFIX) :]
        for c in charts_result
        if isinstance(c, str) and c.startswith(_CHARTS_ERROR_PREFIX)
    ]
    if error_msgs:
        analysis["_charts_error"] = error_msgs[0]

    return {
        "collection": {
            "raw_docs": raw_docs,
            "compressed_summary": collection.get("compressed_summary", {}),
            "source_urls": collection.get("source_urls", []),
            "chapter_plan": collection.get("chapter_plan", []),
            "analysis": analysis,
        },
        "base": {**base, "status": "analyzing"},
    }
