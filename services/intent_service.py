"""
Intent service — classify user input into report / chat / invalid.

Design (AGENTS.md §6.1-compliant):
- Rule-based keywords as primary classifier (fast, no LLM cost)
- Lightweight fallback for ambiguous cases
- Configurable keyword sets via YAML (if needed)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentCategory(str, Enum):
    REPORT = "report"
    CHAT = "chat"
    INVALID = "invalid"


@dataclass
class IntentResult:
    """Result of intent classification."""
    category: IntentCategory
    confidence: float        # 0.0 - 1.0
    matched_rules: list[str] = field(default_factory=list)
    report_type: str = ""     # deep_report / flash_news / earnings_analysis
    reason: str = ""


# ---------------------------------------------------------------------------
# Keyword rule sets
# ---------------------------------------------------------------------------

# Keywords indicating a research report intent
_REPORT_KEYWORDS: list[str] = [
    "研报", "研究报告", "行业分析", "市场分析", "深度分析",
    "帮我写", "撰写", "生成报告", "写一篇", "写一份",
    "投资分析", "行业报告", "市场报告", "趋势分析",
    "财报分析", "财务分析", "季度报告", "年报",
    "新能源汽车", "半导体", "人工智能", "医药",
    "宏观经济", "政策分析", "竞争对手", "SWOT",
    "市场规模", "市场份额", "增长率", "产业链",
    "请分析", "请撰写", "请生成",
]

# Keywords indicating chat / casual
_CHAT_KEYWORDS: list[str] = [
    "你好", "谢谢", "再见", "怎么样", "什么是",
    "解释", "说明", "介绍", "帮助", "帮助文档",
    "功能", "怎么用", "怎么使用", "使用方法",
]

# Keywords indicating invalid / harmful input
_INVALID_KEYWORDS: list[str] = [
    "hack", "破解", "绕过", "越狱",
    "违法", "色情", "赌博", "毒品",
    "恶意代码", "病毒", "木马",
]

# Injection patterns
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:ignore|forget)\s+(?:all\s+)?(?:previous|above)\s+(?:instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are\s+now", re.IGNORECASE),
    re.compile(r"<\|.*?\|>", re.IGNORECASE),
]

# Report type keyword mappings
_REPORT_TYPE_KEYWORDS: dict[str, str] = {
    "快讯": "flash_news",
    "简讯": "flash_news",
    "快报": "flash_news",
    "速览": "flash_news",
    "财报": "earnings_analysis",
    "财务": "earnings_analysis",
    "季报": "earnings_analysis",
    "年报": "earnings_analysis",
    "盈利": "earnings_analysis",
}


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

def classify_intent(query: str) -> IntentResult:
    """Classify a user query into report / chat / invalid.

    Strategy (layered):
    1. Injection detection (security first)
    2. Invalid keyword matching
    3. Report keyword matching (if ≥2 matched → high confidence)
    4. Chat keyword matching
    5. Fallback: treat as report (system purpose is report generation)

    Args:
        query: Raw user input string.

    Returns:
        IntentResult with category, confidence, matched_rules, report_type.
    """
    query_lower = query.lower()

    # ── Layer 1: Injection detection ─────────────────────────────────
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            return IntentResult(
                category=IntentCategory.INVALID,
                confidence=0.95,
                matched_rules=[pattern.pattern],
                reason="Prompt injection detected",
            )

    # ── Layer 2: Invalid / harmful keywords ──────────────────────────
    matched_invalid: list[str] = [
        kw for kw in _INVALID_KEYWORDS if kw in query_lower
    ]
    if matched_invalid:
        return IntentResult(
            category=IntentCategory.INVALID,
            confidence=0.9,
            matched_rules=matched_invalid,
            reason="Harmful content keywords",
        )

    # ── Layer 3: Report keywords ─────────────────────────────────────
    matched_report: list[str] = [
        kw for kw in _REPORT_KEYWORDS if kw in query_lower
    ]
    if len(matched_report) >= 2:
        report_type = _detect_report_type(query)
        return IntentResult(
            category=IntentCategory.REPORT,
            confidence=min(0.6 + 0.1 * len(matched_report), 0.95),
            matched_rules=matched_report,
            report_type=report_type,
            reason=f"Matched {len(matched_report)} report keywords",
        )
    if len(matched_report) == 1:
        # Single keyword — still check for explicit report type hints
        report_type = _detect_report_type(query)
        return IntentResult(
            category=IntentCategory.REPORT,
            confidence=0.5,
            matched_rules=matched_report,
            report_type=report_type,
            reason="Single report keyword match (ambiguous)",
        )

    # ── Layer 4: Chat keywords ───────────────────────────────────────
    matched_chat: list[str] = [
        kw for kw in _CHAT_KEYWORDS if kw in query_lower
    ]
    if matched_chat:
        return IntentResult(
            category=IntentCategory.CHAT,
            confidence=0.7,
            matched_rules=matched_chat,
            reason="Chat keywords detected",
        )

    # ── Layer 5: Length heuristic ────────────────────────────────────
    if len(query) < 5:
        return IntentResult(
            category=IntentCategory.CHAT,
            confidence=0.4,
            reason="Very short query, likely chat",
        )

    # ── Layer 6: Fallback → report ───────────────────────────────────
    return IntentResult(
        category=IntentCategory.REPORT,
        confidence=0.3,
        reason="Fallback (system defaults to report generation)",
    )


def _detect_report_type(query: str) -> str:
    """Detect the specific report type from keywords.

    Returns:
        One of: "" (default/deep_report), "flash_news", "earnings_analysis".
    """
    for kw, rtype in _REPORT_TYPE_KEYWORDS.items():
        if kw in query:
            return rtype
    return ""
