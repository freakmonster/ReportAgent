"""Unit tests for FactStage2Handler + Stage 1.5 Relation Extractor."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.orchestrator.context import PostExecContext  # noqa: E402
from harness.handlers.base import HandlerDecision  # noqa: E402
from harness.handlers.fact_stage2_handler import (  # noqa: E402
    FactStage2Handler,
    extract_qualitative_claims,
)


class TestRelationExtractor:
    """Verify V2.1 Stage 1.5 qualitative assertion detection."""

    def test_detects_comparison(self) -> None:
        claims = extract_qualitative_claims("比亚迪在电池技术上领先宁德时代")
        assert len(claims) >= 1
        assert "比亚迪" in claims[0]["subject"]
        assert claims[0]["relation"] == "领先"
        assert "宁德时代" in claims[0]["object"]

    def test_multiple_comparisons(self) -> None:
        text = "宁德时代在市场份额上超越比亚迪，特斯拉在自动驾驶方面领先蔚来"
        claims = extract_qualitative_claims(text)
        assert len(claims) >= 2

    def test_no_comparison(self) -> None:
        claims = extract_qualitative_claims("新能源汽车市场增长迅速")
        assert claims == []

    def test_various_comparison_keywords(self) -> None:
        for kw in ["领先", "超越", "超过", "优于", "低于", "落后"]:
            claims = extract_qualitative_claims(f"A公司{kw}B公司")
            assert len(claims) >= 1, f"Keyword '{kw}' not detected"


class TestFactStage2Handler:
    """Verify handler integration."""

    @pytest.mark.asyncio
    async def test_no_qualitative_claims_passes(self) -> None:
        handler = FactStage2Handler()
        ctx = PostExecContext(raw_output="新能源汽车销量达300万辆 [1]")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_qualitative_claims_flagged(self) -> None:
        handler = FactStage2Handler()
        ctx = PostExecContext(raw_output="比亚迪在电池技术上领先宁德时代，超过特斯拉")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.FAIL
        assert result.metrics["qualitative_claims_found"] >= 1

    @pytest.mark.asyncio
    async def test_empty_output_passes(self) -> None:
        handler = FactStage2Handler()
        result = await handler.handle(object(), PostExecContext(raw_output=""))
        assert result.decision == HandlerDecision.PASS
