"""
Report service — chapter structure validation, data freshness, compliance rules.

Core compliance rule (V2.0 mandatory):
    Every research report MUST contain a "风险提示" (Risk Warning) section.
    Reports missing this section are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReportStatus(str, Enum):
    VALID = "valid"
    MISSING_RISK = "missing_risk"
    MISSING_CHAPTERS = "missing_chapters"
    DATA_STALE = "data_stale"


@dataclass
class ReportValidationResult:
    """Result of report structure and compliance validation."""

    status: ReportStatus
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    risk_section_present: bool = False
    data_freshness_days: int | None = None
    total_chapters: int = 0
    has_title: bool = False


# Minimum required chapter keywords for a deep research report
_REQUIRED_CHAPTERS: dict[str, list[str]] = {
    "deep_report": [
        "摘要",
        "概述",
        "市场",
        "行业",
        "分析",
        "数据",
        "趋势",
        "竞争",
        "风险",
        "建议",
        "结论",
    ],
    "flash_news": [
        "摘要",
        "要点",
        "数据",
    ],
    "earnings_analysis": [
        "财务",
        "收入",
        "利润",
        "现金流",
        "资产负债",
        "风险",
        "展望",
    ],
}

# Mandatory risk keywords (at least one must appear as a chapter heading)
_RISK_KEYWORDS: list[str] = [
    "风险提示",
    "风险警示",
    "风险因素",
    "风险分析",
    "风险管理",
    "风险",
    "免责声明",
]

# Maximum allowed data age in days
_MAX_DATA_AGE_DAYS: int = 30


def validate_report_structure(
    chapters: list[str],
    report_type: str = "deep_report",
    data_timestamp_days_ago: int = 0,
) -> ReportValidationResult:
    """Validate a report's chapter structure and compliance.

    Checks:
    1. Report has at least a title (first chapter)
    2. Required chapter topics are covered
    3. **Risk warning section is mandatory** (AGENTS.md §6.3 / V2.0)
    4. Data freshness (not older than 30 days)

    Args:
        chapters: List of chapter titles/headings.
        report_type: Template type ("deep_report", "flash_news", "earnings_analysis").
        data_timestamp_days_ago: How many days ago the source data was collected.

    Returns:
        ReportValidationResult with validation status and details.
    """
    result = ReportValidationResult(status=ReportStatus.VALID)

    if not chapters:
        result.status = ReportStatus.MISSING_CHAPTERS
        result.errors.append("Report has no chapters")
        return result

    # ── Title check ──────────────────────────────────────────────────
    result.has_title = True  # first chapter is assumed to be title
    result.total_chapters = len(chapters)

    # ── Required chapters ────────────────────────────────────────────
    required = _REQUIRED_CHAPTERS.get(report_type, _REQUIRED_CHAPTERS["deep_report"])
    text_lower = " ".join(chapters).lower()
    missing: list[str] = []

    for keyword in required:
        # "风险" is checked separately (mandatory, not optional)
        if keyword == "风险":
            continue
        if keyword not in text_lower:
            missing.append(keyword)

    if missing:
        result.warnings.append(f"Missing recommended chapters: {', '.join(missing)}")

    # ── Risk warning (MANDATORY) ─────────────────────────────────────
    has_risk = any(kw in text_lower for kw in _RISK_KEYWORDS)
    result.risk_section_present = has_risk

    if not has_risk:
        result.status = ReportStatus.MISSING_RISK
        result.errors.append(
            "Missing mandatory risk warning section. Every research report must include 风险提示."
        )

    # ── Data freshness ───────────────────────────────────────────────
    result.data_freshness_days = data_timestamp_days_ago
    if data_timestamp_days_ago > _MAX_DATA_AGE_DAYS:
        result.status = ReportStatus.DATA_STALE
        result.errors.append(
            f"Source data is {data_timestamp_days_ago} days old "
            f"(max allowed: {_MAX_DATA_AGE_DAYS} days)"
        )

    # ── Summary ──────────────────────────────────────────────────────
    if result.errors:
        agg = []
        for e in result.errors:
            if "risk" in e.lower():
                agg.append("risk")
            elif "stale" in e.lower() or "old" in e.lower():
                agg.append("stale")
        # If both risk and stale issues exist, report the first critical one
    elif missing:
        result.warnings.append("Consider adding missing recommended chapters")

    return result


def is_report_publishable(result: ReportValidationResult) -> bool:
    """Check if a report can be published based on validation result.

    Returns:
        True if the report is VALID and has the risk section.
    """
    return result.status == ReportStatus.VALID and result.risk_section_present is True


def get_minimum_chapter_count(report_type: str = "deep_report") -> int:
    """Return the minimum expected number of chapters for a report type.

    Args:
        report_type: Template type.

    Returns:
        Minimum chapter count.
    """
    return len(_REQUIRED_CHAPTERS.get(report_type, _REQUIRED_CHAPTERS["deep_report"]))
