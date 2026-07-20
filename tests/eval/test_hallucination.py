"""Hallucination detection evaluation tests.

Covers:
- Prediction statement detection
- Absolute/unsubstantiated language detection
- Internal contradiction detection
- Edge cases (empty text, all-factual text, mixed content)
- Integration with HallucinationHandler interface
- Metrics output validation
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402

from harness.handlers.base import HandlerDecision, HandlerResult  # noqa: E402
from harness.handlers.hallucination_handler import (  # noqa: E402
    HallucinationHandler,
)
from harness.orchestrator.context import PostExecContext  # noqa: E402

# ── Prediction detection ──────────────────────────────────────────────

class TestPredictionDetection:
    """Verify prediction/speculation statement detection."""

    @pytest.mark.asyncio
    async def test_detects_reach_prediction(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="预计2030年市场规模将达到10000亿元")
        result = await handler.handle(None, ctx)
        assert result.decision == HandlerDecision.FAIL
        assert result.metrics["prediction_count"] >= 1

    @pytest.mark.asyncio
    async def test_detects_multiple_predictions(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(
            raw_output="预计销量将增长30%。预测2027年渗透率将达到50%。"
        )
        result = await handler.handle(None, ctx)
        assert result.metrics["prediction_count"] == 2

    @pytest.mark.asyncio
    async def test_no_prediction_in_factual_text(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="2025年销量为300万辆，同比增长15%。")
        result = await handler.handle(None, ctx)
        assert result.metrics["prediction_count"] == 0

    @pytest.mark.asyncio
    async def test_detects_various_prediction_keywords(self) -> None:
        """All prediction variants should be caught (regex requires number immediately after keyword)."""
        handler = HallucinationHandler()
        # These match the regex pattern: keyword -> whitespace* -> number
        predictions = [
            ("预计", "预计2030年市场规模500亿"),
            ("将达到", "将达到500万辆"),
            ("预期", "预期2027年营收1000亿"),
            ("预计将", "预计将达到300亿"),
        ]
        for kw, text in predictions:
            ctx = PostExecContext(raw_output=text)
            result = await handler.handle(None, ctx)
            assert result.metrics["prediction_count"] >= 1, (
                f"Keyword '{kw}' not detected in '{text}'"
            )


# ── Absolute language detection ───────────────────────────────────────

class TestAbsoluteLanguageDetection:
    """Verify detection of unsubstantiated absolute claims."""

    @pytest.mark.asyncio
    async def test_detects_absolute_language(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="这无疑是行业最佳的方案。毋庸置疑这是对的。")
        result = await handler.handle(None, ctx)
        assert result.metrics["absolute_claims"] >= 1

    @pytest.mark.asyncio
    async def test_detects_multiple_absolutes(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="毋庸置疑这是对的，必然取得成功。")
        result = await handler.handle(None, ctx)
        assert result.metrics["absolute_claims"] >= 2

    @pytest.mark.asyncio
    async def test_no_absolute_in_hedged_text(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="这可能是一个较好的方案，但仍有不确定性。")
        result = await handler.handle(None, ctx)
        assert result.metrics["absolute_claims"] == 0

    @pytest.mark.asyncio
    async def test_detects_various_absolute_keywords(self) -> None:
        handler = HallucinationHandler()
        for kw in ["毫无疑问", "毋庸置疑", "必然", "必定", "肯定", "绝对不会", "一定"]:
            ctx = PostExecContext(raw_output=f"{kw}这是最好的选择")
            result = await handler.handle(None, ctx)
            assert result.metrics["absolute_claims"] >= 1, (
                f"Keyword '{kw}' not detected as absolute language"
            )


# ── Contradiction detection ───────────────────────────────────────────

class TestContradictionDetection:
    """Verify internal contradiction detection."""

    @pytest.mark.asyncio
    async def test_detects_contradiction_pair(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="销量增长的同时也在下降。")
        result = await handler.handle(None, ctx)
        assert result.metrics["contradictions"] >= 1

    @pytest.mark.asyncio
    async def test_detects_multiple_contradiction_pairs(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(
            raw_output="盈利但亏损扩大，市场份额提高的同时渗透率降低。"
        )
        result = await handler.handle(None, ctx)
        # "盈利/亏损" + "提高/降低" = 2 pairs
        assert result.metrics["contradictions"] >= 2

    @pytest.mark.asyncio
    async def test_no_contradiction_in_consistent_text(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="销量持续增长，市场份额稳步扩大。")
        result = await handler.handle(None, ctx)
        assert result.metrics["contradictions"] == 0

    @pytest.mark.asyncio
    async def test_all_contradiction_pairs_detected(self) -> None:
        handler = HallucinationHandler()
        pairs = [
            ("增长", "下降"),
            ("上升", "下跌"),
            ("增加", "减少"),
            ("盈利", "亏损"),
            ("扩大", "缩小"),
            ("提高", "降低"),
        ]
        for pos, neg in pairs:
            ctx = PostExecContext(raw_output=f"同时{pos}和{neg}")
            result = await handler.handle(None, ctx)
            assert result.metrics["contradictions"] >= 1, (
                f"Contradiction pair ({pos}, {neg}) not detected"
            )


# ── Edge cases ────────────────────────────────────────────────────────

class TestHallucinationEdgeCases:
    """Boundary conditions for hallucination detection."""

    @pytest.mark.asyncio
    async def test_empty_output_passes(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="")
        result = await handler.handle(None, ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_none_post_ctx_passes(self) -> None:
        handler = HallucinationHandler()
        result = await handler.handle(None, "not_a_postctx")
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_purely_factual_text_passes(self) -> None:
        handler = HallucinationHandler()
        ctx = PostExecContext(
            raw_output="根据国家统计局数据[1]，2025年GDP增长5.2%。"
        )
        result = await handler.handle(None, ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_mixed_content_fails_on_hallucination(self) -> None:
        """Even one hallucination flag should trigger FAIL."""
        handler = HallucinationHandler()
        ctx = PostExecContext(
            raw_output="2025年销量300万辆[1]。预计2030年将达到1000万辆。"
        )
        result = await handler.handle(None, ctx)
        assert result.decision == HandlerDecision.FAIL
        assert result.metrics["prediction_count"] >= 1

    @pytest.mark.asyncio
    async def test_all_three_types_flagged(self) -> None:
        """Text with predictions + absolutes + contradictions should flag all."""
        handler = HallucinationHandler()
        ctx = PostExecContext(
            raw_output="预计将达到500亿，毋庸置疑是最佳，但增长的同时也在下降。"
        )
        result = await handler.handle(None, ctx)
        assert result.metrics["prediction_count"] >= 1
        assert result.metrics["absolute_claims"] >= 1
        assert result.metrics["contradictions"] >= 1
        assert result.decision == HandlerDecision.FAIL

    @pytest.mark.asyncio
    async def test_long_text_with_late_hallucination(self) -> None:
        """Hallucination deep in a long document should still be caught."""
        prefix = "这是一段很长的正常文本。" * 20
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output=prefix + "毋庸置疑这是最佳")
        result = await handler.handle(None, ctx)
        assert result.metrics["absolute_claims"] >= 1


# ── Handler interface compliance ───────────────────────────────────────

class TestHallucinationHandlerInterface:
    """Verify HallucinationHandler conforms to HarnessHandler ABC."""

    def test_handler_name_matches_class(self) -> None:
        handler = HallucinationHandler()
        assert handler.name == "HallucinationHandler"

    def test_result_contains_all_fields(self) -> None:
        """HandlerResult must have decision, detail, metrics fields."""
        result = HandlerResult(decision=HandlerDecision.PASS)
        assert result.decision == HandlerDecision.PASS
        assert isinstance(result.detail, str)
        assert isinstance(result.metrics, dict)

    @pytest.mark.asyncio
    async def test_metrics_always_have_three_keys(self) -> None:
        """Metrics dict should always contain prediction_count, absolute_claims, contradictions."""
        handler = HallucinationHandler()
        ctx = PostExecContext(raw_output="正常文本无异常")
        result = await handler.handle(None, ctx)
        for key in ("prediction_count", "absolute_claims", "contradictions"):
            assert key in result.metrics, f"Missing metrics key: {key}"
            assert isinstance(result.metrics[key], int)
