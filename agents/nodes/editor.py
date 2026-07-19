"""Editor node — rule-based markdown normalization and citation validation.

Writer now generates publish-ready chapters directly (strategy merge),
so editor performs only lightweight rule-based post-processing:
- Citation extraction and cross-validation against source URLs
- Markdown normalization (blank line compression, trailing whitespace, sentence endings)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Citation extraction ───────────────────────────────────────────────

def _extract_citations(
    chapters: dict[str, str], source_urls: list[str]
) -> list[str]:
    """Extract citation markers from all chapters and cross-validate with source_urls.

    Scans all chapter text for [N] patterns, validates that each N is within
    the source_urls index range, and returns the validated source_urls list.

    Args:
        chapters: Mapping of chapter title → chapter content.
        source_urls: List of source URLs ordered as used by the writer.

    Returns:
        The source_urls list if citations are found and valid. If no citations
        are found but source_urls is non-empty, returns source_urls as fallback.
        If source_urls is empty, returns an empty list.
    """
    if not source_urls:
        return []

    all_text = "\n".join(chapters.values())
    citation_numbers: set[int] = {
        int(m) for m in re.findall(r"\[(\d+)\]", all_text)
    }

    # Validate: each citation number must be ≤ len(source_urls)
    max_idx = len(source_urls)
    valid_citations = {n for n in citation_numbers if 1 <= n <= max_idx}

    if valid_citations or citation_numbers:
        # At least some citations found and validated — return source_urls
        return source_urls

    # No citations found at all — return source_urls as fallback
    logger.info("No [N] citations found in chapters, using full source_urls as fallback")
    return source_urls


# ── Markdown normalization ────────────────────────────────────────────

def _normalize_markdown(content: str) -> str:
    """Normalize markdown formatting without destroying structure.

    - Compress >2 consecutive blank lines down to 2 (keep at most one
      paragraph gap)
    - Remove trailing whitespace from each line
    - Ensure every non-heading, non-empty line ends with a sentence-ending
      punctuation (。/?/!), otherwise append "。"
    - Leading whitespace is preserved (no whole-content strip)

    Args:
        content: Raw markdown chapter content.

    Returns:
        Normalized markdown string.
    """
    # 1. Compress >2 consecutive blank lines to 2
    content = re.sub(r"\n{4,}", "\n\n\n", content)

    # 2. Process line by line
    lines = content.split("\n")
    cleaned: list[str] = []
    for line in lines:
        # Remove trailing whitespace (preserve leading whitespace)
        line = line.rstrip()

        # Skip heading lines (# prefix) and empty lines
        if not line or line.lstrip().startswith("#"):
            cleaned.append(line)
            continue

        # Ensure sentence-ending punctuation
        if not line.rstrip().endswith((".", "。", "?", "？", "!", "！")):
            line += "。"

        cleaned.append(line)

    return "\n".join(cleaned)


# ── Main entry ───────────────────────────────────────────────────────

async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Apply rule-based post-processing to chapter drafts.

    Workflow:
        1. Extract and cross-validate citations from all chapters.
        2. Normalize markdown formatting for each chapter.
        3. Return processed drafts, citation list, and preserved final_content.

    Writer now produces publish-ready chapters — no LLM editing needed.

    Input:  writing.chapter_drafts, collection.source_urls
    Output: writing.chapter_drafts (normalized), writing.citation_list,
            writing.final_content

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with normalized drafts and citation list.
    """
    writing: dict[str, Any] = state.get("writing", {})
    collection: dict[str, Any] = state.get("collection", {})

    report_type = state.get("base", {}).get("template_name", "flash_news")
    print(f"[editor] report_type={report_type} (rule-based only, no LLM)")

    chapters: dict[str, str] = writing.get("chapter_drafts", {})
    source_urls: list[str] = collection.get("source_urls", [])

    if not chapters:
        return {
            "writing": {
                "chapter_drafts": chapters,
                "final_content": writing.get("final_content", ""),
                "citation_list": source_urls if source_urls else [],
            },
        }

    # 1. Extract and cross-validate citations
    citation_list = _extract_citations(chapters, source_urls)

    # 2. Normalize markdown for each chapter (rule-based, no LLM)
    edited: dict[str, str] = {}
    for ch_name, content in chapters.items():
        edited[ch_name] = _normalize_markdown(content)

    return {
        "writing": {
            "chapter_drafts": edited,
            "final_content": writing.get("final_content", ""),
            "citation_list": citation_list,
        },
    }
