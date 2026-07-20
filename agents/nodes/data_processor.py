"""Data Processor node — Map-Reduce summarization, paragraph-aware truncation."""

from __future__ import annotations

from typing import Any

from retrieval.chunkers.paragraph_chunker import chunk_text


def _para_truncate(text: str, max_chars: int) -> str:
    """Truncate text at paragraph boundary within max_chars using paragraph_chunker."""
    if len(text) <= max_chars:
        return text
    result = chunk_text(
        text, target_chunk_tokens=int(max_chars / 1.8), min_chars=200, overlap_tokens=0
    )  # result = chunk_text(text, target_chunk_tokens=int(max_chars / 2), min_chars=200)
    # _para_truncate 调用 chunk_text 时用的是默认 overlap_tokens=50 ，但 data_processor 的用途是 压缩塞进 LLM prompt ，不是 RAG 检索。overlap=50 浪费了截断预算
    # 当前 target_chunk_tokens = int(max_chars / 2) （即 2000→1000 tokens），但中文约 1.8 字符/token，1000 tokens ≈ 1800 字符，距离 2000 的预算有 200 字符的空档。对于 6000 字符的 topic 压缩， 3000 * 1.8 = 5400 ，差距更大。改为 target_chunk_tokens = int(max_chars / 1.8) ，使 chunk 的目标大小更贴近字符预算上限。
    if result.chunks:
        parts: list[str] = []
        total = 0
        for c in result.chunks:
            if total + len(c.text) + (2 if parts else 0) > max_chars:
                break
            if parts:
                parts.append("\n\n")
            parts.append(c.text)
            total += len(c.text)
        if parts:
            return "".join(parts)
    return text[:max_chars]


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Compress collected raw documents into per-chapter summaries.

    Input:  collection.raw_docs
    Output: collection.compressed_summary (Dict[chapter_name, summary ≤ 6000 chars])

    Args:
        state: Current ReportState.

    Returns:
        Partial state update with compressed_summary populated.
    """
    collection: dict[str, Any] = state.get("collection", {})
    raw_docs: list[dict[str, str]] = collection.get("raw_docs", [])
    base: dict[str, Any] = state.get("base", {})
    user_query: str = base.get("user_input", "").lower()

    if not raw_docs:
        return state

    # Determine topic buckets: use chapter_plan if available, else fixed topics
    chapter_plan: list[str] = collection.get("chapter_plan", [])
    if chapter_plan:
        topics: dict[str, list[str]] = {ch: [] for ch in chapter_plan}
    else:
        topics = {
            "市场概况": [],
            "竞争格局": [],
            "政策环境": [],
            "技术趋势": [],
            "风险与展望": [],
        }

    for doc in raw_docs:
        content = doc.get("content", "")
        # Assign to best-matching topic
        best_topic = list(topics.keys())[0]  # default: first topic
        best_score = 0
        for topic in topics:
            score = sum(1 for kw in topic.replace("与", " ").split() if kw in content)
            # Bonus: content mentioning the user query matches its topic
            if user_query and user_query in content.lower():
                score += 0.5
            if score > best_score:
                best_score = score
                best_topic = topic
        topics[best_topic].append(_para_truncate(content, 2000))

    # Compress each topic to ≤ 6K
    compressed: dict[str, str] = {}
    for topic, snippets in topics.items():
        combined = " ".join(snippets)
        compressed[topic] = _para_truncate(combined, 6000)

    return {
        "collection": {
            "raw_docs": raw_docs,
            "compressed_summary": compressed,
            "source_urls": collection.get("source_urls", []),
        },
        "base": {**base, "status": "collecting"},
    }
