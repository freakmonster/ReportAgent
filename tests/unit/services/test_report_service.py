"""Unit tests for report_service — structure validation and compliance."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from services.report_service import (  # noqa: E402
    ReportStatus,
    ReportValidationResult,
    get_minimum_chapter_count,
    is_report_publishable,
    validate_report_structure,
)


class TestValidateReportStructure:
    """Verify report chapter structure validation."""

    def test_valid_deep_report(self) -> None:
        """A complete deep report passes validation."""
        chapters = [
            "2026新能源汽车深度研报",
            "摘要",
            "市场概述",
            "行业分析",
            "竞争格局",
            "数据趋势",
            "风险提示",
            "投资建议",
            "结论",
        ]
        result = validate_report_structure(chapters)
        assert result.status == ReportStatus.VALID
        assert result.risk_section_present is True
        assert result.total_chapters == 9

    def test_missing_risk_section(self) -> None:
        """Report without 风险提示 section → MISSING_RISK."""
        chapters = ["标题", "摘要", "市场分析", "数据趋势", "结论"]
        result = validate_report_structure(chapters)
        assert result.status == ReportStatus.MISSING_RISK
        assert "风险提示" in str(result.errors)
        assert result.risk_section_present is False

    def test_risk_keyword_variants(self) -> None:
        """Various risk keyword forms are recognized."""
        for keyword in ["风险提示", "风险警示", "风险因素", "风险分析", "免责声明"]:
            result = validate_report_structure(["标题", "摘要", keyword, "结论"])
            assert result.risk_section_present is True, f"Keyword '{keyword}' not recognized"

    def test_empty_chapters(self) -> None:
        """Empty chapter list → MISSING_CHAPTERS."""
        result = validate_report_structure([])
        assert result.status == ReportStatus.MISSING_CHAPTERS
        assert "no chapters" in str(result.errors).lower()

    def test_stale_data(self) -> None:
        """Data older than 30 days → DATA_STALE."""
        chapters = ["标题", "摘要", "市场分析", "风险提示", "结论"]
        result = validate_report_structure(chapters, data_timestamp_days_ago=45)
        assert result.status == ReportStatus.DATA_STALE
        assert "old" in str(result.errors).lower()

    def test_data_within_threshold(self) -> None:
        """Data within 30 days is fine."""
        chapters = ["标题", "摘要", "市场分析", "风险提示", "结论"]
        result = validate_report_structure(chapters, data_timestamp_days_ago=10)
        assert result.status == ReportStatus.VALID

    def test_flash_news_template(self) -> None:
        """Flash news has lighter chapter requirements."""
        chapters = ["快讯标题", "要点", "数据摘要", "风险提示"]
        result = validate_report_structure(chapters, report_type="flash_news")
        assert result.status == ReportStatus.VALID

    def test_earnings_template(self) -> None:
        """Earnings analysis requires financial chapters."""
        chapters = ["腾讯财报", "收入分析", "利润分析", "现金流", "风险提示", "展望"]
        result = validate_report_structure(chapters, report_type="earnings_analysis")
        assert result.status == ReportStatus.VALID

    def test_missing_both_risk_and_chapters(self) -> None:
        """Missing risk section AND recommended chapters → MISSING_RISK (risk takes priority)."""
        chapters = ["标题"]
        result = validate_report_structure(chapters)
        assert result.status == ReportStatus.MISSING_RISK


class TestReportPublishable:
    """Verify publishability check."""

    def test_valid_report_is_publishable(self) -> None:
        """A valid report with risk section is publishable."""
        chapters = ["标题", "摘要", "风险提示"]
        result = validate_report_structure(chapters)
        assert is_report_publishable(result) is True

    def test_missing_risk_not_publishable(self) -> None:
        """Report without risk section cannot be published."""
        chapters = ["标题", "摘要", "分析"]
        result = validate_report_structure(chapters)
        assert is_report_publishable(result) is False


class TestMinimumChapters:
    """Verify minimum chapter count."""

    def test_deep_report_minimum(self) -> None:
        assert get_minimum_chapter_count("deep_report") > 0

    def test_flash_news_minimum(self) -> None:
        assert get_minimum_chapter_count("flash_news") == 3

    def test_unknown_report_type_defaults(self) -> None:
        """Unknown type falls back to deep_report minimum."""
        assert get_minimum_chapter_count("unknown_type") == get_minimum_chapter_count("deep_report")
