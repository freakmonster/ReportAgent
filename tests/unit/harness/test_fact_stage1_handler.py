"""Unit tests for FactStage1Handler — regex data entity extraction."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.handlers.base import HandlerDecision  # noqa: E402
from harness.handlers.fact_stage1_handler import (  # noqa: E402
    DataClaim,
    FactStage1Handler,
    extract_data_claims,
)
from harness.orchestrator.context import PostExecContext  # noqa: E402


class TestExtractDataClaims:
    """Verify regex-based data entity extraction."""

    def test_extract_percentages(self) -> None:
        claims = extract_data_claims("销量增长了45%，市场份额达到30.5%")
        assert len(claims) >= 2
        types = {c.entity_type for c in claims}
        assert "percentage" in types

    def test_extract_currency(self) -> None:
        claims = extract_data_claims("营收达到100亿元，利润15.2亿元")
        assert len(claims) >= 2
        assert claims[0].entity_type == "currency"

    def test_extract_dates(self) -> None:
        claims = extract_data_claims("2024年Q1同比增长25%")
        assert len(claims) >= 2
        types = {c.entity_type for c in claims}
        assert "date" in types

    def test_cited_claims_detected(self) -> None:
        claims = extract_data_claims("销量增长45% [1]")
        assert len(claims) >= 1
        assert claims[0].has_citation is True

    def test_uncited_claims(self) -> None:
        claims = extract_data_claims("市场规模约为500亿元")
        assert len(claims) >= 1
        assert claims[0].has_citation is False

    def test_no_claims(self) -> None:
        claims = extract_data_claims("这是一段没有任何数据的描述性文字。")
        assert claims == []


class TestFactStage1Handler:
    """Verify handler integration."""

    @pytest.fixture
    def handler(self) -> FactStage1Handler:
        return FactStage1Handler()

    @pytest.mark.asyncio
    async def test_all_cited_passes(self, handler: FactStage1Handler) -> None:
        ctx = PostExecContext(raw_output="销量增长25% [1]，营收达100亿元 [2]")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_uncited_triggers_fail(self, handler: FactStage1Handler) -> None:
        ctx = PostExecContext(raw_output="销量增长25%，营收达100亿元，份额扩大至40%")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.FAIL
        assert result.metrics["citation_rate"] < 1.0

    @pytest.mark.asyncio
    async def test_empty_output_passes(self, handler: FactStage1Handler) -> None:
        ctx = PostExecContext(raw_output="")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.PASS
