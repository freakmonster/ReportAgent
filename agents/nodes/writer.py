"""Writer node — V2.1 chapter-level context isolation, real LLM generation.

Reads collection.compressed_summary and generates chapter drafts via DeepSeek.
Each chapter gets ≤ 6K chars of context to avoid Lost-in-the-Middle.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from config.settings import settings
from models.llm_providers.deepseek_client import DeepSeekClient  # kept for test mocking

logger = logging.getLogger(__name__)


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Write report chapters one by one using DeepSeek LLM.

    Input:  collection.compressed_summary (topic → text ≤ 6K)
           collection.source_urls
    Output: writing.chapter_drafts, writing.citation_list

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with chapter_drafts populated.
    """
    collection: dict[str, Any] = state.get("collection", {})
    base: dict[str, Any] = state.get("base", {})
    compressed: dict[str, str] = collection.get("compressed_summary", {})
    source_urls: list[str] = collection.get("source_urls", [])
    user_input: str = base.get("user_input", "")

    # Dynamic max_tokens based on report type
    report_type: str = base.get("template_name", "flash_news")
    max_tokens: int = 4000 if report_type in ("deep_report", "earnings_analysis") else 2000
    print(f"[writer] report_type={report_type}, max_tokens={max_tokens}")

    # Read analysis from data_analyst node
    analysis: dict[str, Any] = collection.get("analysis", {})
    analysis_parts: list[str] = []
    if analysis.get("doc_count"):
        quality = analysis.get("data_quality", "unknown")
        analysis_parts.append(f"Sources: {analysis['doc_count']} documents ({analysis.get('total_chars', 0)} chars, quality: {quality})")
    if analysis.get("key_metrics"):
        metrics_str = ", ".join(analysis["key_metrics"][:12])
        analysis_parts.append(f"Key Metrics: {metrics_str}")
    if analysis.get("insights"):
        insights_str = "; ".join(analysis["insights"][:5])
        analysis_parts.append(f"Insights: {insights_str}")
    analysis_summary = " | ".join(analysis_parts) if analysis_parts else ""
    chart_count = len(analysis.get("charts", []))

    if not compressed:
        # Fallback: workflows without data_processor (flash_news, earnings_analysis)
        # build a summary directly from raw_docs
        raw_docs: list[dict[str, Any]] = collection.get("raw_docs", [])
        if raw_docs:
            combined_parts: list[str] = []
            total_chars = 0
            max_chars = 6000
            for doc in raw_docs[:10]:
                content = doc.get("content", "")
                if not content:
                    continue
                # Truncate each doc to ~3000 chars to fit multiple docs
                snippet = content[:3000]
                combined_parts.append(snippet)
                total_chars += len(snippet)
                if total_chars >= max_chars:
                    break
            if combined_parts:
                compressed = {"摘要": "\n\n---\n\n".join(combined_parts)[:max_chars]}
                logger.info(
                    "writer.fallback_raw_docs docs=%d chars=%d",
                    len(combined_parts), total_chars,
                )

        if not compressed:
            return {
                "writing": {
                    "chapter_drafts": {"摘要": "暂无数据可供撰写报告。"},
                    "final_content": "",
                    "citation_list": source_urls if source_urls else [],
                },
                "base": {**base, "status": "writing"},
            }

    # ── Select LLM provider based on state.model (dynamic user choice) ──
    model: str = base.get("model", "deepseek-flash")
    from models.llm_providers.resolver import resolve_llm_client
    client = resolve_llm_client(model)
    print(f"[writer] model={model} | provider={type(client).__name__}")

    # ── Parallel chapter generation ──────────────────────────────────
    async def _generate_one(ch_name: str, ch_context: str) -> tuple[str, str]:
        """Generate a single chapter with full fallback chain. Returns (ch_name, content)."""
        try:
            content = await _generate_chapter(
                client, ch_name, ch_context, user_input, analysis_summary, chart_count, max_tokens, source_urls,
            )
        except Exception as e:
            print(f"[writer] LLM call failed for chapter '{ch_name}': {type(e).__name__}: {e}")
            traceback.print_exc()
            logger.warning("Writer LLM call failed for chapter '%s', using fallback", ch_name, exc_info=True)
            return ch_name, _fallback_chapter(ch_name, ch_context)

        # Strip the heading prefix to check actual body content
        heading = f"## {ch_name}\n\n"
        body = content[len(heading):].strip() if content.startswith(heading) else content.strip()
        if len(body) < 50:
            # Possible rate-limit empty response from parallel calls — retry once
            print(f"[writer] LLM returned too-short/empty content for chapter '{ch_name}' (body_len={len(body)}), retrying once")
            logger.warning("Writer LLM returned too-short content for chapter '%s' (body_len=%d), retrying once", ch_name, len(body))
            await asyncio.sleep(1)
            try:
                content = await _generate_chapter(
                    client, ch_name, ch_context, user_input, analysis_summary, chart_count, max_tokens, source_urls,
                )
                body = content[len(heading):].strip() if content.startswith(heading) else content.strip()
            except Exception as e:
                print(f"[writer] LLM retry also failed for chapter '{ch_name}': {type(e).__name__}: {e}")
                logger.warning("Writer LLM retry also failed for chapter '%s', using fallback", ch_name, exc_info=True)
                return ch_name, _fallback_chapter(ch_name, ch_context)

            if len(body) < 50:
                print(f"[writer] LLM retry also returned too-short content for chapter '{ch_name}' (body_len={len(body)}), falling back")
                logger.warning("Writer LLM retry also returned too-short content for chapter '%s' (body_len=%d), using fallback", ch_name, len(body))
                return ch_name, _fallback_chapter(ch_name, ch_context)

        return ch_name, _post_process_chapter(ch_name, content)

    tasks = [_generate_one(ch_name, ch_context) for ch_name, ch_context in compressed.items()]
    results: list[tuple[str, str] | Exception] = await asyncio.gather(*tasks, return_exceptions=True)

    drafts: dict[str, str] = {}
    for result in results:
        if isinstance(result, Exception):
            # asyncio.gather captured an unexpected exception at the gather level
            # (should not happen with the try/except inside _generate_one, but defend anyway)
            print(f"[writer] unexpected gather exception: {type(result).__name__}: {result}")
            continue
        ch_name, content = result
        drafts[ch_name] = content

    citation_list = source_urls if source_urls else []

    return {
        "writing": {
            "chapter_drafts": drafts,
            "final_content": "",
            "citation_list": citation_list,
        },
        "base": {**base, "status": "writing"},
    }


async def _generate_chapter(
    client: Any,
    chapter_title: str,
    chapter_data: str,
    user_query: str = "",
    analysis_summary: str = "",
    chart_count: int = 0,
    max_tokens: int = 2000,
    source_urls: list[str] | None = None,
) -> str:
    """Call LLM to generate one chapter.

    Args:
        client: LLM client instance (DeepSeekClient or QwenClient).
        chapter_title: Name of the chapter.
        chapter_data: Source data for this chapter (≤ 6K chars).
        user_query: Original user query for topic anchoring.
        analysis_summary: Formatted analysis data from data_analyst node.
        chart_count: Number of charts available from data_analyst node.
        max_tokens: Maximum tokens for LLM response (default 2000).

    Returns:
        Generated chapter content in Markdown.
    """
    try:
        from models.prompts.prompt_manager import get_prompt_manager
        pm = get_prompt_manager()
        citation_info = ""
        if source_urls:
            citation_info = "\n".join(
                f"  [{i}] {url}" for i, url in enumerate(source_urls, 1)
            )
        prompt = pm.render(
            "writer",
            chapter_title=chapter_title,
            chapter_data=chapter_data[:6000],
            user_query=user_query,
            analysis_summary=analysis_summary,
            chart_count=chart_count,
            citation_sources=citation_info,
        )
    except Exception:
        prompt = (
            f"你是一名专业的研究报告撰写员。请根据以下资料，撰写关于「{user_query}」的章节「{chapter_title}」的内容。"
            f"\n\n资料：\n{chapter_data[:6000]}\n\n"
            f"请用中文撰写，语言专业、客观、数据准确。包含引用标注。"
        )

    response = await client.chat(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"请撰写章节：{chapter_title}"},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )

    content = response["choices"][0]["message"]["content"]
    return f"## {chapter_title}\n\n{content.strip()}"


def _fallback_chapter(chapter_title: str, chapter_data: str) -> str:
    """Generate a fallback chapter when LLM is unavailable."""
    return (
        f"## {chapter_title}\n\n"
        f"（注：LLM 生成失败，以下为基于原始数据的摘要）\n\n"
        f"{chapter_data[:500]}...\n\n"
    )


def _post_process_chapter(chapter_title: str, content: str) -> str:
    """Clean up a generated chapter: deduplicate headings, remove meta-commentary."""
    import re

    # 1. Remove duplicate chapter title headings
    lines = content.split("\n")
    seen_heading = False
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == f"## {chapter_title}":
            if seen_heading:
                continue
            seen_heading = True
        cleaned.append(line)

    content = "\n".join(cleaned)

    # 2. Remove meta-commentary patterns
    meta_patterns = [
        r"根据您提供的.*?撰写如下内容",
        r"鉴于.*?未在输入中指明",
        r"本章节以.*?为示例",
        r"您可依据实际.*?替换与细化",
        r"基于您提供的.*?我已为您",
        r"以下为基于",
    ]
    for pat in meta_patterns:
        content = re.sub(pat, "", content)

    # 3. Strip leading/trailing whitespace
    content = content.strip()

    return content
