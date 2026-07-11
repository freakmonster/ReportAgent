"""段落感知分层分块器 —— 按段落边界 + 分隔符递归切分，保持上下文连贯。
原semantic_chunker.py 变更→ paragraph_chunker.py"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

# ── Token estimation ────────────────────────────────────────────────────

def count_tokens_estimate(text: str) -> int:
    """估算 Token 数——针对 bge-m3 tokenizer 校准。

    中文 ≈ 1.8 字符/Token，英文 ≈ 4.5 字符/Token。
    """
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    english = len(text) - chinese
    return int(chinese / 1.8 + english / 4.5)


# ── Natural boundary helper ─────────────────────────────────────────────

_NATURAL_BOUNDARIES = "。！？；\n，"

def _find_split_point(text: str, target: int, window: int = 50) -> int:
    """在 target 位置附近查找最近的自然分隔符作为切割点。

    向左搜索 window 个字符，返回最后一个自然边界（\n、。！？；，）之后的位置。
    找不到边界时回退到 target 字符硬切。

    Args:
        text: 要切割的文本。
        target: 目标切割位置（字符索引）。
        window: 向左搜索的窗口宽度（字符数）。

    Returns:
        切割点字符索引（边界字符之后）。
    """
    search_start = max(0, target - window)
    for boundary in _NATURAL_BOUNDARIES:
        idx = text.rfind(boundary, search_start, target + 1)
        if idx >= search_start:
            return idx + 1  # 在边界字符之后切
    return target  # 找不到边界，回退到字符硬切


# ── Data classes ────────────────────────────────────────────────────────

@dataclass
class Chunk:
    """文本块"""
    text: str
    index: int
    char_count: int = 0
    token_estimate: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.text)
        self.token_estimate = count_tokens_estimate(self.text)


@dataclass
class ChunkResult:
    """分块结果"""
    source: str
    chunks: list[Chunk] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def total_chars(self) -> int:
        return sum(c.char_count for c in self.chunks)

    @property
    def total_tokens_estimate(self) -> int:
        return sum(c.token_estimate for c in self.chunks)


# ── Paragraph splitting ─────────────────────────────────────────────────

# 段落分隔正则（按优先级）
_PARAGRAPH_SPLITTERS: list[re.Pattern] = [
    re.compile(r"\n\s*\n"),                      # 双换行（段落边界）
    re.compile(r"\n(?=[#＃])"),                     # 标题前换行
    re.compile(r"(?<=[。！？.!?])\s*\n"),            # 句末换行
]

# Markdown 标题模式
_HEADING_PATTERN = re.compile(r"^(#{1,6}\s|[#＃]\s)", re.MULTILINE)

# 递归切分分隔符层级（从宽到窄）
# 移除了 " "（空格）— 它对英文破坏性太强，对中文无意义，段落边界已由 _PARAGRAPH_SPLITTERS 处理
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", ""]

# 递归深度上限（防止恶意输入栈溢出）
_MAX_RECURSION_DEPTH = 20


def _split_into_paragraphs(text: str) -> list[str]:
    """将文本拆分为段落列表。"""
    for pattern in _PARAGRAPH_SPLITTERS:
        parts = pattern.split(text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    # 兜底：按单换行拆分
    lines = text.split("\n")
    return [line.strip() for line in lines if line.strip()]


def _merge_short_paragraphs(
    paragraphs: list[str],
    min_chars: int = 200,
) -> list[str]:
    """合并过短段落，保持语义完整性。"""
    merged: list[str] = []
    buffer = ""
    for para in paragraphs:
        if len(buffer) + len(para) < min_chars:
            buffer = (buffer + "\n" + para).strip()
        else:
            if buffer:
                merged.append(buffer)
            buffer = para
    if buffer:
        merged.append(buffer)
    return merged


def _respect_heading_boundaries(paragraphs: list[str]) -> list[str]:
    """对含标题的段落进行微调——标题单独起段，确保不被合并到其他内容中。"""
    result: list[str] = []
    for para in paragraphs:
        m = _HEADING_PATTERN.match(para)
        if m:
            heading_end = m.end()
            heading = para[:heading_end].strip()
            rest = para[heading_end:].strip()
            if rest:
                result.append(heading)
                result.append(rest)
            else:
                result.append(para)
        else:
            result.append(para)
    return result


# ── Recursive split ─────────────────────────────────────────────────────

def recursive_split_paragraph(
    text: str,
    target_tokens: int,
    min_chunk_tokens: int = 50,
    _depth: int = 0,
) -> list[str]:
    """递归切分超长段落，确保每段 Token 数 ≤ target_tokens。

    策略：优先按自然分隔符切，切出碎片太短则合并，递归兜底。

    Args:
        text: 要切分的段落文本。
        target_tokens: 目标每段 Token 上限。
        min_chunk_tokens: 最小段长，避免碎片化。
        _depth: 内部递归深度计数器（调用方不传此参数）。

    Returns:
        切分后的子段列表。
    """
    if count_tokens_estimate(text) <= target_tokens:
        return [text]

    # 递归深度保护
    if _depth >= _MAX_RECURSION_DEPTH:
        return _hard_split(text, target_tokens)

    for sep in _SEPARATORS:
        if sep == "":
            return _hard_split(text, target_tokens)

        if sep in text:
            parts = text.split(sep)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) <= 1:
                continue

            merged_parts = []
            buffer = ""
            for p in parts:
                if count_tokens_estimate(buffer + p) < min_chunk_tokens * 2:
                    buffer = (buffer + sep + p).strip()
                else:
                    if buffer:
                        merged_parts.append(buffer)
                    buffer = p
            if buffer:
                merged_parts.append(buffer)

            result = []
            for p in merged_parts:
                result.extend(recursive_split_paragraph(p, target_tokens, min_chunk_tokens, _depth + 1))
            return result

    return [text]


def _hard_split(text: str, target_tokens: int) -> list[str]:
    """无分隔符时的兜底策略：按字符硬切，尽量对齐词边界。

    使用 _find_split_point 在每个目标位置附近寻找自然边界。
    找不到边界时才回退到纯字符硬切。
    """
    chunk_size = int(target_tokens * 1.8)
    if len(text) <= chunk_size:
        return [text]

    result = []
    pos = 0
    while pos < len(text):
        target = min(pos + chunk_size, len(text))
        if target >= len(text):
            # 最后一段直接添加
            segment = text[pos:].strip()
            if segment:
                result.append(segment)
            break
        # 在目标位置附近找边界
        split_at = _find_split_point(text, target)
        if split_at <= pos:
            split_at = target  # 边界搜索失败，回退到硬切
        segment = text[pos:split_at].strip()
        if segment:
            result.append(segment)
        pos = split_at
    return result


# ── Main API ────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    source: str = "",
    *,
    target_chunk_tokens: int = 512,
    min_chars: int = 200,
    overlap_tokens: int = 50,
) -> ChunkResult:
    """对文本进行段落感知分层分块。

    分块策略：
    1. 按段落边界切分
    2. 合并过短段落
    3. 尊重标题边界
    4. 递归切分超长段落
    5. 按目标 Token 数聚合为 chunks（含精确 Overlap）

    Args:
        text: 输入文本。
        source: 来源标识（用于日志/追踪）。
        target_chunk_tokens: 目标每块 Token 数。
        min_chars: 最小段落合并阈值（字符数）。
        overlap_tokens: 相邻 chunk 重叠的 Token 估计量。

    Returns:
        ChunkResult 含分块列表和元数据。
    """
    if not text:
        return ChunkResult(source=source)

    # 防止 overlap 超过目标 chunk 大小
    overlap_tokens = min(overlap_tokens, max(0, target_chunk_tokens // 3))

    # Step 1: 拆分为段落
    paragraphs = _split_into_paragraphs(text)

    # Step 2: 合并过短段落
    paragraphs = _merge_short_paragraphs(paragraphs, min_chars=min_chars)

    # Step 3: 尊重标题边界
    paragraphs = _respect_heading_boundaries(paragraphs)

    # Step 4: 递归切分超长段落
    expanded_paragraphs = []
    for para in paragraphs:
        para_tokens = count_tokens_estimate(para)
        if para_tokens > target_chunk_tokens:
            sub_paras = recursive_split_paragraph(para, target_chunk_tokens)
            expanded_paragraphs.extend(sub_paras)
        else:
            expanded_paragraphs.append(para)
    paragraphs = expanded_paragraphs

    # Step 5: 按目标 Token 数聚合（含精确 Overlap）
    chunks: list[Chunk] = []
    buffer_parts: list[str] = []
    buffer_tokens: int = 0
    previous_overlap_text = ""

    for idx, para in enumerate(paragraphs):
        para_tokens = count_tokens_estimate(para)

        if buffer_tokens > 0 and buffer_tokens + para_tokens > target_chunk_tokens:
            chunk_text_content = "\n\n".join(buffer_parts)
            chunks.append(Chunk(text=chunk_text_content, index=len(chunks)))

            if overlap_tokens > 0:
                # 从 chunk 末尾向前找自然边界作为 overlap 起点
                search_start = max(0, len(chunk_text_content) - int(overlap_tokens * 1.8) - 80)
                split_at = _find_split_point(chunk_text_content, search_start + 80, 80)
                if split_at >= len(chunk_text_content):
                    # 找不到边界，回退到字符硬截
                    overlap_chars = int(overlap_tokens * 1.8)
                    previous_overlap_text = chunk_text_content[-overlap_chars:].strip()
                else:
                    previous_overlap_text = chunk_text_content[split_at:].strip()
            else:
                previous_overlap_text = ""

            buffer_parts = [previous_overlap_text] if previous_overlap_text else []
            buffer_tokens = count_tokens_estimate(previous_overlap_text) if previous_overlap_text else 0

        buffer_parts.append(para)
        buffer_tokens += para_tokens

    # Step 6: 剩余内容
    if buffer_parts:
        chunk_text_content = "\n\n".join(buffer_parts)
        chunks.append(Chunk(text=chunk_text_content, index=len(chunks)))

    result = ChunkResult(source=source, chunks=chunks)

    logger.debug(
        "Text chunked",
        source=source,
        total_chunks=result.total_chunks,
        total_tokens=result.total_tokens_estimate,
    )
    return result


def chunk_documents(
    documents: dict[str, str],
    *,
    target_chunk_tokens: int = 512,
    min_chars: int = 200,
    overlap_tokens: int = 50,
) -> dict[str, ChunkResult]:
    """批量分块多个文档。

    Args:
        documents: {source_id: text} 映射。
        target_chunk_tokens: 每块目标 Token 数。
        min_chars: 最小段落合并阈值。
        overlap_tokens: 相邻 chunk 重叠 Token 数。

    Returns:
        {source_id: ChunkResult} 映射。
    """
    results: dict[str, ChunkResult] = {}
    for source_id, text in documents.items():
        results[source_id] = chunk_text(
            text,
            source=source_id,
            target_chunk_tokens=target_chunk_tokens,
            min_chars=min_chars,
            overlap_tokens=overlap_tokens,
        )
    return results
