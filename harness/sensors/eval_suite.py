"""
Evaluation suite — automated quality scoring across four dimensions.

Dimensions:
1. Completeness — does the report cover all required sections?
2. Accuracy — data claims backed by citations?
3. Citation quality — are source references present and valid?
4. Logical flow — does the content follow a coherent structure?
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalScores:
    """Four-dimension quality scores (0.0 - 1.0 each)."""

    completeness: float = 0.0
    accuracy: float = 0.0
    citation_quality: float = 0.0
    logical_flow: float = 0.0

    @property
    def overall(self) -> float:
        """Weighted average of all dimensions."""
        return round(
            (
                self.completeness * 0.3
                + self.accuracy * 0.3
                + self.citation_quality * 0.2
                + self.logical_flow * 0.2
            ),
            2,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "completeness": self.completeness,
            "accuracy": self.accuracy,
            "citation_quality": self.citation_quality,
            "logical_flow": self.logical_flow,
            "overall": self.overall,
        }


# Required sections for a complete report
_REQUIRED_SECTIONS: list[str] = [
    "摘要",
    "概述",
    "市场",
    "分析",
    "数据",
    "竞争",
    "风险",
    "建议",
]

# Logical transition patterns (good flow)
_TRANSITION_PATTERNS: list[str] = [
    "因此",
    "然而",
    "此外",
    "另一方面",
    "综上所述",
    "根据",
    "数据显示",
    "值得关注",
    "值得注意的是",
    "综上所述",
    "总之",
    "由此可见",
]


def _has_section(text: str, keyword: str) -> bool:
    """Check if a section keyword appears as a heading or prominent text."""
    return keyword in text


def score_completeness(text: str) -> float:
    """Score how complete the report is based on required sections.

    Returns 1.0 if all required sections are present, proportionally less otherwise.
    """
    if not text:
        return 0.0
    covered = sum(1 for kw in _REQUIRED_SECTIONS if _has_section(text, kw))
    return round(covered / len(_REQUIRED_SECTIONS), 2)


def score_accuracy(cited_claims: int, total_claims: int) -> float:
    """Score accuracy based on citation coverage of data claims.

    Args:
        cited_claims: Number of claims with citations.
        total_claims: Total number of data claims.

    Returns:
        0.0 if no claims, 1.0 if all cited, proportional otherwise.
    """
    if total_claims == 0:
        return 0.0
    if total_claims < 3:
        return 0.5  # Too few claims to assess
    return round(cited_claims / total_claims, 2)


def score_citation_quality(text: str) -> float:
    """Score citation quality based on presence of reference markers.

    Returns 1.0 if 5+ citations present, scaling down.
    """
    if not text:
        return 0.0
    citations = re.findall(r"\[\d+\]", text)
    count = len(citations)
    return round(min(count / 5.0, 1.0), 2)


def score_logical_flow(text: str) -> float:
    """Score logical flow by counting transition phrases and section structure.

    Returns 1.0 for strong flow indicators, lower for disorganized content.
    """
    if not text:
        return 0.0

    transitions = sum(1 for tp in _TRANSITION_PATTERNS if tp in text)
    headings = len(re.findall(r"^#{1,3}\s", text, re.MULTILINE))

    # Normalize: 5+ transitions and 3+ headings → 1.0
    t_score = min(transitions / 5.0, 1.0) * 0.5
    h_score = min(headings / 3.0, 1.0) * 0.5
    return round(t_score + h_score, 2)


def evaluate_report(text: str) -> EvalScores:
    """Compute all four quality dimensions for a report.

    Args:
        text: Full report content as Markdown.

    Returns:
        EvalScores with completeness, accuracy, citation_quality, logical_flow.
    """
    # Count data claims for accuracy metric
    claims = re.findall(r"\d+\.?\d*\s*%|\d+(?:万|亿)", text)
    cited = len(re.findall(r"\[\d+\]", text))

    return EvalScores(
        completeness=score_completeness(text),
        accuracy=score_accuracy(cited, len(claims)),
        citation_quality=score_citation_quality(text),
        logical_flow=score_logical_flow(text),
    )
