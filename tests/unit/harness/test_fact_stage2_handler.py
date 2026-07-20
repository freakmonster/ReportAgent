"""Unit tests for FactStage2Handler — Stage 1.5 Relation Extractor + Stage 2 MCP/LLM Verification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from harness.handlers.base import HandlerDecision  # noqa: E402
from harness.handlers.fact_stage2_handler import (  # noqa: E402
    FactStage2Handler,
    _verify_claim_via_llm,
    _verify_claim_via_mcp,
    _verify_claims,
    extract_qualitative_claims,
)
from harness.orchestrator.context import PostExecContext  # noqa: E402

# ── Stage 1.5: Relation Extractor ─────────────────────────────────────

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

    def test_deepseek_vs_openai_detection(self) -> None:
        claims = extract_qualitative_claims("DeepSeek在推理性能上超越了OpenAI的GPT-4")
        assert len(claims) >= 1
        assert "DeepSeek" in claims[0]["subject"] or claims[0]["subject"] in "DeepSeek"
        assert claims[0]["relation"] in ("超越", "超越了")


# ── Stage 2: MCP Verification ─────────────────────────────────────────

class TestMCPVerification:
    """Verify MCP-based claim verification."""

    @pytest.mark.asyncio
    async def test_mcp_verifies_claim(self) -> None:
        """MCP returns search results containing both entities → verified."""
        claim = {"subject": "比亚迪", "relation": "领先", "object": "宁德时代", "sentence": "比亚迪领先宁德时代"}
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "results": [
                {"snippet": "比亚迪和宁德时代在电池市场展开竞争"},
            ]
        }

        with patch(
            "mcp_tools.mcp_client.mcp_client.call",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.mcp_search_url = "http://localhost:8001"
                result = await _verify_claim_via_mcp(claim)

        assert result["verified"] is True
        assert result["method"] == "mcp_web_search"

    @pytest.mark.asyncio
    async def test_mcp_no_evidence(self) -> None:
        """MCP returns results without both entities → not verified."""
        claim = {"subject": "UnknownCorp", "relation": "领先", "object": "OtherCorp", "sentence": "UnknownCorp领先OtherCorp"}
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "results": [
                {"snippet": "Unrelated text about AI technology"},
            ]
        }

        with patch(
            "mcp_tools.mcp_client.mcp_client.call",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.mcp_search_url = "http://localhost:8001"
                result = await _verify_claim_via_mcp(claim)

        assert result["verified"] is False
        assert result["method"] == "mcp_web_search"

    @pytest.mark.asyncio
    async def test_mcp_unavailable(self) -> None:
        """MCP server not configured → mcp_unavailable."""
        claim = {"subject": "A", "relation": "领先", "object": "B", "sentence": "A领先B"}

        with patch("config.settings.settings") as mock_settings:
            mock_settings.mcp_search_url = ""
            result = await _verify_claim_via_mcp(claim)

        assert result["verified"] is False
        assert result["method"] == "mcp_unavailable"

    @pytest.mark.asyncio
    async def test_mcp_connection_error(self) -> None:
        """MCP call raises exception → mcp_exception."""
        claim = {"subject": "A", "relation": "领先", "object": "B", "sentence": "A领先B"}

        with patch(
            "mcp_tools.mcp_client.mcp_client.call",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.mcp_search_url = "http://localhost:8001"
                result = await _verify_claim_via_mcp(claim)

        assert result["verified"] is False
        assert result["method"] == "mcp_exception"


# ── Stage 2: LLM Verification ─────────────────────────────────────────

class TestLLMVerification:
    """Verify LLM-based claim verification (fallback)."""

    @pytest.mark.asyncio
    async def test_llm_confirms_claim(self) -> None:
        """LLM returns verified=true → verified."""
        claim = {"subject": "比亚迪", "relation": "领先", "object": "宁德时代", "sentence": "比亚迪领先宁德时代"}
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"verified": true, "reason": "行业报告确认"}'))
        ]

        with patch(
            "models.llm_providers.deepseek_client.DeepSeekClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _verify_claim_via_llm(claim)

        assert result["verified"] is True
        assert result["method"] == "llm_evaluation"

    @pytest.mark.asyncio
    async def test_llm_denies_claim(self) -> None:
        """LLM returns verified=false → not verified."""
        claim = {"subject": "UnknownCorp", "relation": "领先", "object": "OtherCorp", "sentence": "UnknownCorp领先OtherCorp"}
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"verified": false, "reason": "无法确认"}'))
        ]

        with patch(
            "models.llm_providers.deepseek_client.DeepSeekClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _verify_claim_via_llm(claim)

        assert result["verified"] is False
        assert result["method"] == "llm_evaluation"

    @pytest.mark.asyncio
    async def test_llm_exception(self) -> None:
        """LLM call fails → llm_exception."""
        claim = {"subject": "A", "relation": "领先", "object": "B", "sentence": "A领先B"}

        with patch(
            "models.llm_providers.deepseek_client.DeepSeekClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(side_effect=Exception("API Error"))
            mock_client_cls.return_value = mock_client

            result = await _verify_claim_via_llm(claim)

        assert result["verified"] is False
        assert result["method"] == "llm_exception"

    @pytest.mark.asyncio
    async def test_llm_unparseable_response(self) -> None:
        """LLM returns non-JSON → llm_unparseable."""
        claim = {"subject": "A", "relation": "领先", "object": "B", "sentence": "A领先B"}
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="I cannot verify this claim."))
        ]

        with patch(
            "models.llm_providers.deepseek_client.DeepSeekClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _verify_claim_via_llm(claim)

        assert result["verified"] is False
        assert result["method"] == "llm_unparseable"


# ── Stage 2: Batch Verification ───────────────────────────────────────

class TestBatchVerification:
    """Verify batch claim verification flow."""

    @pytest.mark.asyncio
    async def test_all_verified(self) -> None:
        """All claims verified → verified_count == total."""
        claims = [
            {"subject": "A", "relation": "领先", "object": "B", "sentence": "A领先B"},
            {"subject": "C", "relation": "超越", "object": "D", "sentence": "C超越D"},
        ]

        with patch(
            "harness.handlers.fact_stage2_handler._verify_claim_via_mcp",
            new_callable=AsyncMock,
            return_value={"verified": True, "evidence": "found", "method": "mcp_web_search"},
        ):
            result = await _verify_claims(claims)

        assert result["verified_count"] == 2
        assert result["unverified_count"] == 0
        assert result["total_checked"] == 2

    @pytest.mark.asyncio
    async def test_some_unverified(self) -> None:
        """Some claims unverified → partial verification."""
        claims = [
            {"subject": "A", "relation": "领先", "object": "B", "sentence": "A领先B"},
            {"subject": "C", "relation": "超越", "object": "D", "sentence": "C超越D"},
        ]

        # First claim verified by MCP, second fails both MCP and LLM
        async def mock_mcp(claim):
            if claim["subject"] == "A":
                return {"verified": True, "evidence": "found", "method": "mcp_web_search"}
            return {"verified": False, "evidence": "", "method": "mcp_error"}

        async def mock_llm(claim):
            return {"verified": False, "evidence": "unknown", "method": "llm_evaluation"}

        with patch(
            "harness.handlers.fact_stage2_handler._verify_claim_via_mcp",
            side_effect=mock_mcp,
        ):
            with patch(
                "harness.handlers.fact_stage2_handler._verify_claim_via_llm",
                side_effect=mock_llm,
            ):
                result = await _verify_claims(claims)

        assert result["verified_count"] == 1
        assert result["unverified_count"] == 1

    @pytest.mark.asyncio
    async def test_max_claims_limit(self) -> None:
        """Only verify up to _MAX_CLAIMS_TO_VERIFY claims."""
        claims = [{"subject": f"E{i}", "relation": "领先", "object": f"F{i}", "sentence": ""} for i in range(10)]

        with patch(
            "harness.handlers.fact_stage2_handler._verify_claim_via_mcp",
            new_callable=AsyncMock,
            return_value={"verified": True, "evidence": "found", "method": "mcp_web_search"},
        ):
            result = await _verify_claims(claims)

        assert result["total_checked"] == 5  # _MAX_CLAIMS_TO_VERIFY = 5
        assert result["total_found"] == 10


# ── Handler Integration ───────────────────────────────────────────────

class TestFactStage2Handler:
    """Verify handler integration with full Stage 1.5 + Stage 2 flow."""

    @pytest.mark.asyncio
    async def test_no_qualitative_claims_passes(self) -> None:
        handler = FactStage2Handler()
        ctx = PostExecContext(raw_output="新能源汽车销量达300万辆 [1]")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_qualitative_claims_flagged_and_verified(self) -> None:
        """Claims found → Stage 2 attempts verification → result depends on outcome."""
        handler = FactStage2Handler()
        ctx = PostExecContext(raw_output="比亚迪在电池技术上领先宁德时代")

        with patch(
            "harness.handlers.fact_stage2_handler._verify_claim_via_mcp",
            new_callable=AsyncMock,
            return_value={"verified": True, "evidence": "confirmed", "method": "mcp_web_search"},
        ):
            result = await handler.handle(object(), ctx)

        assert result.decision == HandlerDecision.PASS
        assert result.metrics["qualitative_claims_found"] >= 1
        assert result.metrics["unverified"] == 0

    @pytest.mark.asyncio
    async def test_unverified_claims_flagged(self) -> None:
        """MCP and LLM both fail → claims remain unverified → FAIL."""
        handler = FactStage2Handler()
        ctx = PostExecContext(raw_output="比亚迪在电池技术上领先特斯拉")

        with patch(
            "harness.handlers.fact_stage2_handler._verify_claim_via_mcp",
            new_callable=AsyncMock,
            return_value={"verified": False, "evidence": "", "method": "mcp_exception"},
        ):
            with patch(
                "harness.handlers.fact_stage2_handler._verify_claim_via_llm",
                new_callable=AsyncMock,
                return_value={"verified": False, "evidence": "unknown", "method": "llm_exception"},
            ):
                result = await handler.handle(object(), ctx)

        assert result.decision == HandlerDecision.FAIL
        assert result.metrics["unverified_via_llm"] >= 1

    @pytest.mark.asyncio
    async def test_empty_output_passes(self) -> None:
        handler = FactStage2Handler()
        result = await handler.handle(object(), PostExecContext(raw_output=""))
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_no_post_exec_context_passes(self) -> None:
        handler = FactStage2Handler()
        result = await handler.handle(object(), "not a PostExecContext")
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_metrics_include_details(self) -> None:
        """Verification metrics include claim-level details."""
        handler = FactStage2Handler()
        ctx = PostExecContext(raw_output="比亚迪在电池技术上领先宁德时代")

        with patch(
            "harness.handlers.fact_stage2_handler._verify_claim_via_mcp",
            new_callable=AsyncMock,
            return_value={"verified": True, "evidence": "confirmed", "method": "mcp_web_search"},
        ):
            result = await handler.handle(object(), ctx)

        assert "details" in result.metrics
        assert len(result.metrics["details"]) >= 1
        assert result.metrics["details"][0]["verified"] is True

    @pytest.mark.asyncio
    async def test_multiple_claims_in_batch(self) -> None:
        """Multiple qualitative claims → all verified in batch."""
        handler = FactStage2Handler()
        ctx = PostExecContext(raw_output="A公司领先B公司，C公司超越D公司")

        with patch(
            "harness.handlers.fact_stage2_handler._verify_claim_via_mcp",
            new_callable=AsyncMock,
            return_value={"verified": True, "evidence": "confirmed", "method": "mcp_web_search"},
        ):
            result = await handler.handle(object(), ctx)

        assert result.decision == HandlerDecision.PASS
        assert result.metrics["qualitative_claims_found"] == 2
