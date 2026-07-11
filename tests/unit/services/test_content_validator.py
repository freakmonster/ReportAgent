"""Unit tests for content_validator — sensitive content and Markdown checks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from services.validators.content_validator import (  # noqa: E402
    ContentValidationResult,
    check_sensitive_content,
    validate_content,
    validate_markdown_format,
)


class TestSensitiveContent:
    """Verify sensitive content detection."""

    def test_clean_content_passes(self) -> None:
        """Normal report content has no sensitive matches."""
        text = "新能源汽车市场在2026年Q2表现出强劲增长势头，销量同比增长45%。"
        has_sensitive, hits = check_sensitive_content(text)
        assert has_sensitive is False
        assert hits == []

    def test_political_extremism_detected(self) -> None:
        """Political extremism patterns are caught."""
        has_sensitive, hits = check_sensitive_content("推翻政权的方案如下")
        assert has_sensitive is True
        assert len(hits) >= 1

    def test_weapons_pattern_detected(self) -> None:
        """Weapons/drugs patterns are caught."""
        has_sensitive, hits = check_sensitive_content("如何购买毒品和制造武器")
        assert has_sensitive is True

    def test_high_return_fraud_detected(self) -> None:
        """Investment fraud patterns are caught."""
        has_sensitive, hits = check_sensitive_content("这是一个稳赚不赔的高收益投资项目")
        assert has_sensitive is True

    def test_censored_blocks_detected(self) -> None:
        """█████ censored blocks are flagged."""
        has_sensitive, hits = check_sensitive_content("本文内容████████████已删除")
        assert has_sensitive is True
        assert "censored" in str(hits).lower() or "█" in str(hits)

    def test_mixed_clean_and_sensitive(self) -> None:
        """Even a single sensitive hit in large text is caught."""
        text = "正常内容。" * 100 + "制造爆炸物的方法如下"
        has_sensitive, _ = check_sensitive_content(text)
        assert has_sensitive is True


class TestMarkdownFormat:
    """Verify Markdown format validation."""

    def test_valid_markdown(self) -> None:
        """Well-formed Markdown passes."""
        text = "# Title\n\n## Section\n\nContent with [link](https://example.com)"
        errors = validate_markdown_format(text)
        assert errors == []

    def test_no_headings(self) -> None:
        """Missing headings are flagged."""
        errors = validate_markdown_format("Plain text without any headings")
        assert "heading" in str(errors).lower()

    def test_broken_links(self) -> None:
        """Empty URL links are flagged."""
        text = "Click [here]() and [also]()"
        errors = validate_markdown_format(text)
        assert len(errors) >= 1
        assert "broken link" in str(errors).lower()

    def test_image_missing_alt_text(self) -> None:
        """Image without alt text is flagged."""
        text = "![ ](https://example.com/img.png)"
        errors = validate_markdown_format(text)
        assert "alt" in str(errors).lower() or "alt" in " ".join(errors).lower()


class TestValidateContent:
    """Verify combined content validation."""

    def test_clean_report_passes(self) -> None:
        """A clean well-formatted report with citations passes."""
        text = (
            "# 新能源汽车行业分析\n\n"
            "## 概述\n\n"
            "近年新能源汽车市场快速增长 [1]。\n\n"
            "## 风险提示\n\n"
            "本文数据来源参见引用 [1] [2]。\n"
        )
        result = validate_content(text)
        assert result.is_valid is True
        assert result.has_sensitive_content is False
        assert result.has_format_errors is False
        assert result.has_citations is True

    def test_sensitive_content_blocks_validation(self) -> None:
        """Sensitive content causes validation failure."""
        result = validate_content("# Title\n\n稳赚不赔的投资项目推荐")
        assert result.is_valid is False
        assert result.has_sensitive_content is True

    def test_missing_citations_flagged(self) -> None:
        """Missing citations are flagged as format error."""
        result = validate_content("# Title\n\nContent without any citations.")
        assert result.has_citations is False
        assert "citation" in str(result.format_errors).lower()
        assert result.is_valid is False


class TestContentValidationResult:
    """Verify the result dataclass."""

    def test_defaults(self) -> None:
        """Default values are correct."""
        r = ContentValidationResult(is_valid=True)
        assert r.has_sensitive_content is False
        assert r.has_format_errors is False
        assert r.sensitive_hits == []
        assert r.format_errors == []
        assert r.citation_count == 0
