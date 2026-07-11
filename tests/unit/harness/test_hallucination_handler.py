"""Unit tests for HallucinationHandler — unsupported claim detection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.orchestrator.context import PostExecContext  # noqa: E402
from harness.handlers.base import HandlerDecision  # noqa: E402
from harness.handlers.hallucination_handler import HallucinationHandler  # noqa: E402


class TestHallucinationHandler:
    """Verify hallucination detection logic."""

    @pytest.mark.asyncio
    async def test_clean_output_passes(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="新能源汽车销量达到300万辆，同比增长45%。")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_prediction_detected(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="预计2027年市场规模将达到5000亿元，将会超越传统燃油车。")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.FAIL
        assert result.metrics["prediction_count"] >= 2

    @pytest.mark.asyncio
    async def test_absolute_claims_detected(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="这毫无疑问是最好的选择，必定会成功。")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.FAIL
        assert result.metrics["absolute_claims"] >= 1

    @pytest.mark.asyncio
    async def test_contradiction_detected(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="销量增长的同时，市场反而下降。盈利却亏损。")
        result = await handler.handle(object(), ctx)
        assert result.metrics["contradictions"] >= 2

    @pytest.mark.asyncio
    async def test_empty_output_passes(self) -> None:
        handler = HallucinationHandler()
        result = await handler.handle(object(), PostExecContext(raw_output=""))
        assert result.decision == HandlerDecision.PASS
