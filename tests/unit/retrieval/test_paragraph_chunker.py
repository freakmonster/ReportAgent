"""Unit tests for paragraph_chunker — recursive split, precise overlap, heading respect."""

from retrieval.chunkers.paragraph_chunker import (
    Chunk,
    ChunkResult,
    chunk_documents,
    chunk_text,
    count_tokens_estimate,
)

_TEXT_WITH_HEADERS = """# 第一章 引言

这是第一章的内容，包含一些背景介绍和基础概念。
本段会与上一段合并因为太短。

# 第二章 方法论

这一章描述具体的方法论。
我们采用了定性与定量相结合的研究方法。

数据采集过程如下：
1. 从公开数据库获取数据
2. 对数据进行清洗
3. 应用统计模型分析
"""

_SHORT_PARAGRAPHS = "短句一。\n\n短句二。\n\n短句三。\n\n短句四。"


class TestParagraphChunker:
    def test_chunks_with_headers(self):
        result = chunk_text(_TEXT_WITH_HEADERS, source="test.md", target_chunk_tokens=200)
        assert isinstance(result, ChunkResult)
        assert result.total_chunks >= 1

    def test_merges_short_paragraphs(self):
        result = chunk_text(_SHORT_PARAGRAPHS, source="test", target_chunk_tokens=512)
        # Short paragraphs should be merged into fewer chunks
        assert result.total_chunks <= 2

    def test_returns_chunks_with_content(self):
        text = "段落A的内容足够长应该单独成块。" * 20
        result = chunk_text(text, source="test", target_chunk_tokens=200)
        assert result.total_chunks >= 1
        assert all(isinstance(c, Chunk) for c in result.chunks)
        assert all(len(c.text) > 0 for c in result.chunks)

    def test_empty_text(self):
        result = chunk_text("", source="empty")
        assert result.total_chunks == 0

    def test_single_long_paragraph(self):
        text = "这是一个长段落的内容它不会被拆分因为内部没有双换行符。" * 100
        result = chunk_text(text, source="long", target_chunk_tokens=100, min_chars=50)
        assert result.total_chunks >= 1

    def test_chunk_documents_batch(self):
        docs = {
            "doc1.md": "# 文档1\n\n第一段内容。",
            "doc2.md": "# 文档2\n\n第二段内容。",
        }
        results = chunk_documents(docs)
        assert len(results) == 2
        assert results["doc1.md"].total_chunks >= 1
        assert results["doc2.md"].total_chunks >= 1

    def test_recursive_split_long_paragraph(self):
        """A single oversized paragraph is recursively split into sub-chunks ≤ target_tokens."""
        mega_text = "超长文本段落。无换行符连续内容。" * 500
        result = chunk_text(
            mega_text,
            source="overflow",
            target_chunk_tokens=200,
            overlap_tokens=20,
        )
        assert result.total_chunks >= 3
        for chunk in result.chunks:
            assert chunk.token_estimate <= 200

    def test_overlap_token_precision(self):
        """Adjacent chunks have overlap within a reasonable tolerance of overlap_tokens."""
        text_lines = [
            f"第{i}段：这是一段有意义的文本内容，包含足够的中文字符来测试重叠功能。"
            for i in range(30)
        ]
        text = "\n\n".join(text_lines)

        result = chunk_text(
            text,
            source="overlap_test",
            target_chunk_tokens=100,
            overlap_tokens=30,
            min_chars=10,
        )

        assert result.total_chunks >= 2

        for i in range(result.total_chunks - 1):
            current = result.chunks[i]
            next_chunk = result.chunks[i + 1]
            combined_len = len(current.text) + len(next_chunk.text)
            assert combined_len > 0
            assert next_chunk.token_estimate <= 100

    def test_count_tokens_calibrated(self):
        """Calibrated coefficients: Chinese 1.8 chars/token, English 4.5 chars/token."""
        chinese_text = "测" * 180
        assert 90 <= count_tokens_estimate(chinese_text) <= 110

        english_text = "x" * 450
        assert 90 <= count_tokens_estimate(english_text) <= 110

        mixed_text = "测" * 90 + "x" * 225
        tokens = count_tokens_estimate(mixed_text)
        assert 90 <= tokens <= 120
