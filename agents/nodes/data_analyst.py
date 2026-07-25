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
_CHARTS_PLAN_ERROR_PREFIX = "__CHARTS_PLAN_ERR__:"


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


async def _plan_charts(
    analysis: dict[str, Any],
    compressed_summary: str,
    raw_docs_excerpt: str,
    user_query: str,
    model: str,
    max_retries: int = 2,
) -> list[dict[str, Any]]:
    """Call LLM to determine whether charts are needed and plan them.

    The LLM reads the document summary and decides:
    - Whether meaningful chartable data exists (same-unit, coherent)
    - What chart types to generate
    - Precise labels and values from the content

    Args:
        analysis: Dict with doc_count, key_metrics, data_quality, insights.
        compressed_summary: Compressed document content summary.
        user_query: Original user query for context.
        model: LLM model string.
        max_retries: Maximum LLM call attempts.

    Returns:
        List of chart plan dicts with keys: type, title, x_label, y_label, data, x_ticks?
        Returns empty list if LLM decides no charts needed or call fails.
    """
    if not compressed_summary or analysis.get("doc_count", 0) < 2:
        logger.info("data_analyst: skip chart planning — no content or too few docs")
        return []

    # Chart planning is a metadata task — always use flash regardless of user model
    plan_model = "deepseek-flash" if model in ("deepseek-pro",) else model

    try:
        from models.llm_providers.resolver import resolve_llm_client
        from models.prompts.prompt_manager import get_prompt_manager

        pm = get_prompt_manager()
        prompt = pm.render(
            "data_analyst_chart_plan",
            user_query=user_query[:500],
            doc_count=analysis.get("doc_count", 0),
            data_quality=analysis.get("data_quality", "unknown"),
            compressed_summary=compressed_summary[:6000],
            raw_docs_excerpt=raw_docs_excerpt[:2000],
        )

        client = resolve_llm_client(plan_model)
        for attempt in range(max_retries):
            response = await client.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请分析文档内容，决定是否需要图表并输出JSON计划"},
                ],
                temperature=0.1 + attempt * 0.1,
                max_tokens=1500,
            )

            content: str = response["choices"][0]["message"]["content"]
            content = content.strip()
            print(f"[data_analyst] chart_plan LLM raw (attempt {attempt+1}): {content[:500]}", flush=True)

            # Extract JSON from possible markdown code fences
            import json

            json_str = content
            # Strip ```json ... ``` fences if present
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if fence_match:
                json_str = fence_match.group(1).strip()
            # Strip leading/trailing braces whitespace
            json_str = json_str.strip()
            # Find the first { and last }
            start = json_str.find("{")
            end = json_str.rfind("}")
            if start >= 0 and end > start:
                json_str = json_str[start:end + 1]

            try:
                plan = json.loads(json_str)
            except json.JSONDecodeError:
                if attempt < max_retries - 1:
                    print(f"[data_analyst] chart_plan JSON parse FAILED (attempt {attempt+1}), retrying...", flush=True)
                    continue
                print(f"[data_analyst] chart_plan JSON parse FAILED after {max_retries} attempts", flush=True)
                return []

            if not plan.get("should_generate", False):
                print(
                    f"[data_analyst] LLM decided NO charts needed — "
                    f"{plan.get('reason', 'no reason given')}",
                    flush=True,
                )
                return []

            charts = plan.get("charts", [])
            if not charts:
                print("[data_analyst] LLM returned empty charts list", flush=True)
                return []

            # Validate chart plans — build type → plan map
            type_to_plan: dict[str, dict[str, Any]] = {}
            valid_types = {"bar", "pie", "line", "area", "scatter", "radar", "funnel", "dual_axes", "histogram"}
            for chart in charts:
                ct = chart.get("type", "")
                if ct not in valid_types:
                    print(f"[data_analyst] chart_plan: INVALID chart type {ct!r}, skipping", flush=True)
                    continue
                raw_data = chart.get("data")
                if isinstance(raw_data, dict):
                    if not raw_data:
                        print(f"[data_analyst] chart_plan: chart {chart.get('title', '?')!r} has EMPTY data, skipping", flush=True)
                        continue
                elif isinstance(raw_data, list):
                    if not raw_data:
                        print(f"[data_analyst] chart_plan: chart {chart.get('title', '?')!r} has EMPTY data, skipping", flush=True)
                        continue
                    # Convert line-chart list to dict format for downstream processing
                    chart["data"] = {"series": raw_data}
                else:
                    print(f"[data_analyst] chart_plan: chart {chart.get('title', '?')!r} has INVALID data type {type(raw_data).__name__}, skipping", flush=True)
                    continue
                type_to_plan[ct] = chart

            if not type_to_plan:
                print("[data_analyst] LLM returned plans but ALL failed validation", flush=True)
                return []

            # Randomly pick ONE from suitable_types ∩ valid plans
            import random as _random

            suitable_raw = plan.get("suitable_types", [])
            suitable_types = [t for t in suitable_raw if t in type_to_plan]

            if not suitable_types:
                # Fallback: if suitable_types is missing/invalid, pick from all valid plans
                suitable_types = list(type_to_plan.keys())

            picked_type = _random.choice(suitable_types)
            picked_plan = type_to_plan[picked_type]
            print(
                f"[data_analyst] LLM suitable={suitable_types} → randomly picked {picked_type!r}",
                flush=True,
            )

            return [picked_plan]

        return []
    except Exception as exc:
        print(f"[data_analyst] chart_plan LLM call FAILED: {exc}", flush=True)
        return []



def _build_chart_args_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Convert LLM chart plan dict to MCP chart tool arguments.

    LLM plan format:
      Bar/Pie/Area/Scatter/Funnel/Histogram:
        {type, title, x_label, y_label, data: {label: value, ...}}
      Line:
        {type, title, x_label, y_label, data: [values], x_ticks: [...]}
      Radar/Dual_axes:
        {type, title, x_label, y_label, data: {series: [values], ...}, x_ticks: [...]}

    Tool argument format (bar/line/area/scatter/radar/funnel/dual_axes/histogram):
      {title, x_label, y_label, data: {series: [values]}, x_ticks: [labels]}

    Tool argument format (pie):
      {title, data: {label: value, ...}}
    """
    chart_type: str = plan.get("type", "bar")
    title: str = plan.get("title", "Chart")
    llm_data: dict[str, Any] = plan.get("data", {})

    if chart_type == "pie":
        return {"title": title, "data": dict(llm_data)}

    # Determine if data is already {series: [values]} (line/radar/dual_axes) or {label: value} (bar/area/scatter/funnel/histogram)
    first_val = next(iter(llm_data.values()), None)
    if isinstance(first_val, list):
        # Multi-series chart (line from converted array, radar, dual_axes):
        # data already in {series_name: [values]} format, pass through
        return {
            "title": title,
            "x_label": plan.get("x_label", "X"),
            "y_label": plan.get("y_label", "Y"),
            "data": {k: v for k, v in llm_data.items()},
            "x_ticks": plan.get("x_ticks", []),
        }

    # Single-series chart (bar, area, scatter, funnel, histogram):
    # convert {label: value} → {data: {series: [values]}, x_ticks: [labels]}
    x_ticks: list[str] = list(llm_data.keys())
    values: list[float] = [float(v) for v in llm_data.values()]

    return {
        "title": title,
        "x_label": plan.get("x_label", "X"),
        "y_label": plan.get("y_label", "Y"),
        "data": {"Metrics": values},
        "x_ticks": x_ticks,
    }


async def _generate_charts(
    analysis: dict[str, Any],
    compressed_summary: str = "",
    raw_docs_excerpt: str = "",
    user_query: str = "",
    model: str = "deepseek-flash",
) -> list[dict[str, Any]]:
    """Chart generation: LLM-driven planning.

    1. LLM reads compressed_summary → decides IF charts needed and PLANS them
    2. If LLM returns a plan → generate charts from plan data via AntV MCP
    3. If LLM says "no charts" or fails → gracefully skip (no fallback)

    Args:
        analysis: Dict with key_metrics, doc_count, insights, etc.
        compressed_summary: Compressed document content for LLM to analyze.
        user_query: Original user query for context.
        model: LLM model string.

    Returns:
        List of chart entry dicts (may be empty).
    """
    if analysis.get("doc_count", 0) < 2:
        logger.info(
            "data_analyst: skip charts — doc_count=%d < 2",
            analysis.get("doc_count", 0),
        )
        return []

    # ── Phase 1: LLM-driven chart planning ───────────────────────────
    plan_charts: list[dict[str, Any]] = []
    plan_error: str | None = None

    if compressed_summary:
        print(f"[data_analyst] Entering LLM chart planning phase (summary={len(compressed_summary)} chars, raw_excerpt={len(raw_docs_excerpt)} chars)", flush=True)
        try:
            plan_charts = await _plan_charts(analysis, compressed_summary, raw_docs_excerpt, user_query, model)
        except Exception as exc:
            plan_error = str(exc)
            print(f"[data_analyst] chart_plan exception: {exc}", flush=True)
    else:
        print("[data_analyst] No compressed_summary, SKIPPING LLM plan phase", flush=True)

    if plan_charts:
        # Generate charts from LLM plan
        charts: list[dict[str, Any]] = []
        for plan in plan_charts:
            chart_type: str = plan.get("type", "bar")
            try:
                chart_args = _build_chart_args_from_plan(plan)

                from mcp_tools.registry import registry as _registry

                tool_name = f"mcp_generate_{chart_type}_chart"
                tool = await _registry.get_tool(tool_name)
                if tool is None:
                    print(f"[data_analyst] {tool_name} NOT available, skip chart {plan.get('title')!r}", flush=True)
                    continue

                result_data = await tool(chart_args)
                if isinstance(result_data, dict):
                    if result_data.get("error") or result_data.get("degraded"):
                        print(f"[data_analyst] LLM-planned {chart_type} chart FAILED: {result_data.get('error', result_data)}", flush=True)
                        continue
                    image_base64 = result_data.get("image_base64", "")
                else:
                    image_base64 = ""

                if image_base64:
                    charts.append({
                        "chart_type": chart_type,
                        "title": plan.get("title", "Chart"),
                        "image_base64": image_base64,
                    })
            except Exception as exc:
                print(f"[data_analyst] LLM-planned {chart_type} chart generation ERROR: {exc}", flush=True)
                continue

        if charts:
            print(
                f"[data_analyst] LLM-planned charts DONE — count={len(charts)} "
                f"types={[c['chart_type'] for c in charts]}",
                flush=True,
            )
            return charts

        # LLM planned charts but all failed to generate → skip
        print(f"[data_analyst] LLM planned {len(plan_charts)} charts but ALL FAILED, skipping", flush=True)
        return []

    # LLM was consulted (compressed_summary was available) → respect its decision
    if compressed_summary and not plan_error:
        print("[data_analyst] LLM decided no charts needed", flush=True)
        return []

    # LLM either never consulted (no compressed_summary) or had an error → skip
    print("[data_analyst] No charts generated (LLM path failed or unavailable)", flush=True)
    return []



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
        user_model: str = base.get("model", "deepseek-flash")
        # Insights generation is a metadata task — always use flash
        model: str = "deepseek-flash" if user_model in ("deepseek-pro",) else user_model
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
    compressed = collection.get("compressed_summary", {})
    compressed_summary: str = (
        "\n\n".join(
            f"## {topic}\n{txt}" for topic, txt in compressed.items()
        )
        if isinstance(compressed, dict)
        else str(compressed)
    )
    print(
        f"[data_analyst] compressed_summary_len={len(compressed_summary)} "
        f"from {len(compressed) if isinstance(compressed, dict) else 0} topics "
        f"— {'USE' if compressed_summary else 'SKIP'} LLM plan",
        flush=True,
    )
    user_query: str = base.get("user_input", "")
    model_str: str = base.get("model", "deepseek-flash")

    # Build raw docs excerpt for LLM chart planning (compressed_summary may lose numbers)
    raw_docs = collection.get("raw_docs", [])
    raw_excerpt = "\n\n---\n\n".join(
        d.get("content", "")[:600] for d in raw_docs[:3]
    )[:2500]
    print(
        f"[data_analyst] raw_excerpt_len={len(raw_excerpt)} from {len(raw_docs)} raw docs "
        f"(trimmed to 2500)",
        flush=True,
    )

    charts_result = await _generate_charts(
        analysis.copy(),
        compressed_summary=compressed_summary,
        raw_docs_excerpt=raw_excerpt,
        user_query=user_query,
        model=model_str,
    )
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
