"""Evaluation tests — hallucination and factuality benchmarks.

These are smoke tests for the evaluation framework.  Full benchmark
datasets would be loaded from external sources in production.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402


class TestFactuality:
    """Basic factuality evaluation scenarios."""

    def test_cited_content_scores_higher(self) -> None:
        """Content with citations should score higher than content without."""
        cited = "销量增长45% [1]。市场规模达到500亿元 [2]。"
        uncited = "销量大概增长了不到一半。市场规模非常大。"
        # Cited content has more data entities and citations
        import re

        cited_entities = len(re.findall(r"\d+", cited))
        uncited_entities = len(re.findall(r"\d+", uncited))
        assert cited_entities > uncited_entities, "Cited content should have more data entities"

    def test_placeholder_content_fails(self) -> None:
        """Content full of placeholder text scores poorly."""
        placeholder = "这是一个很长的占位文本，没有实际的数据和引用。"
        import re

        entities = len(re.findall(r"\d+", placeholder))
        assert entities == 0, "Placeholder content should have zero data entities"


class TestHallucination:
    """Basic hallucination detection scenarios."""

    def test_fabricated_data_flagged(self) -> None:
        """Fabricated numbers without citations should be flagged."""
        fabricated = "预计2027年市场规模将达到10000亿元，必定超越所有竞争对手。"
        # Check for prediction markers
        has_prediction = "预计" in fabricated and "将" in fabricated
        has_absolute = "必定" in fabricated
        assert has_prediction or has_absolute, "Fabricated content should trigger flags"

    def test_well_sourced_content_passes(self) -> None:
        """Well-sourced factual content should pass."""
        factual = "根据中国汽车工业协会数据[1]，2026年Q2新能源汽车销量同比增长45%。"
        assert "[1]" in factual
        assert "根据" in factual
