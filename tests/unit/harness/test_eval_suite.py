"""Unit tests for EvalSuite — four-dimension quality scoring."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.sensors.eval_suite import (  # noqa: E402
    EvalScores,
    evaluate_report,
    score_accuracy,
    score_citation_quality,
    score_completeness,
    score_logical_flow,
)


class TestCompleteness:
    def test_full_report(self) -> None:
        text = "# 摘要\n概述\n市场\n分析\n数据\n竞争\n风险提示\n建议"
        assert score_completeness(text) == 1.0

    def test_partial_report(self) -> None:
        text = "# 摘要\n市场分析\n数据"
        assert 0 < score_completeness(text) < 1.0

    def test_empty(self) -> None:
        assert score_completeness("") == 0.0


class TestAccuracy:
    def test_all_cited(self) -> None:
        assert score_accuracy(5, 5) == 1.0

    def test_half_cited(self) -> None:
        assert score_accuracy(3, 6) == 0.5

    def test_no_claims(self) -> None:
        assert score_accuracy(0, 0) == 0.0

    def test_few_claims(self) -> None:
        assert score_accuracy(1, 1) == 0.5


class TestCitationQuality:
    def test_many_citations(self) -> None:
        text = "[1] [2] [3] [4] [5] [6]"
        assert score_citation_quality(text) == 1.0

    def test_few_citations(self) -> None:
        text = "[1] [2]"
        assert score_citation_quality(text) == 0.4

    def test_empty(self) -> None:
        assert score_citation_quality("") == 0.0


class TestLogicalFlow:
    def test_well_structured(self) -> None:
        text = "# 标题\n\n因此数据显示 另外 根据 此外 值得注意的是\n## 第二章\n### 第三章"
        assert score_logical_flow(text) > 0.5

    def test_disorganized(self) -> None:
        assert score_logical_flow("random text") == 0.0

    def test_empty(self) -> None:
        assert score_logical_flow("") == 0.0


class TestEvaluateReport:
    def test_full_evaluation(self) -> None:
        text = (
            "# 摘要\n## 概述\n市场分析 [1]\n数据 [2]\n竞争 [3]\n"
            "风险提示\n建议\n因此 此外 数据显示 值得注意的是 根据"
        )
        scores = evaluate_report(text)
        assert isinstance(scores, EvalScores)
        assert 0 <= scores.overall <= 1.0

    def test_to_dict(self) -> None:
        scores = EvalScores(completeness=0.8, accuracy=0.6, citation_quality=0.5, logical_flow=0.7)
        d = scores.to_dict()
        assert d["overall"] == pytest.approx(0.66, abs=0.02)
        assert "completeness" in d

    def test_empty_report(self) -> None:
        scores = evaluate_report("")
        assert scores.overall == 0.0
