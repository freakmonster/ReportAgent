"""
Hallucination Handler — detect unsupported statements and high-risk segments.

Flags content that:
- Makes unsupported predictions ("will reach", "is expected to grow")
- Uses absolute language without evidence ("must", "undoubtedly")
- Contains internal contradictions
"""

from __future__ import annotations

import re
from typing import Any

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler


# Prediction / speculation patterns
_PREDICTION_RE = re.compile(
    r"(?:预计|预测|将会|将达到|有望|预计将|预期)\s*(\d+\.?\d*)",
    re.IGNORECASE,
)

# Absolute / unsubstantiated language
_ABSOLUTE_RE = re.compile(
    r"(?:毫无疑问|毋庸置疑|必然|必定|肯定|绝对不会|一定)",
    re.IGNORECASE,
)

# Internal contradiction markers
_CONTRADICTION_PAIRS: list[tuple[str, str]] = [
    ("增长", "下降"), ("上升", "下跌"), ("增加", "减少"),
    ("盈利", "亏损"), ("扩大", "缩小"), ("提高", "降低"),
]


class HallucinationHandler(HarnessHandler):
    """Detects potentially unsupported or hallucinated content."""

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Scan output for hallucination markers."""
        from harness.orchestrator.context import PostExecContext

        if not isinstance(post_ctx, PostExecContext):
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No post-exec context, skipping hallucination check",
            )

        output = post_ctx.raw_output
        if not output:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="Empty output",
            )

        # ── Prediction detection ─────────────────────────────────────
        predictions = _PREDICTION_RE.findall(output)
        pred_count = len(predictions)

        # ── Absolute language ────────────────────────────────────────
        absolutes = _ABSOLUTE_RE.findall(output)
        abs_count = len(absolutes)

        # ── Contradiction detection ──────────────────────────────────
        contradiction_count = 0
        for pos_word, neg_word in _CONTRADICTION_PAIRS:
            has_pos = pos_word in output
            has_neg = neg_word in output
            if has_pos and has_neg:
                contradiction_count += 1

        warnings: list[str] = []
        if pred_count > 0:
            warnings.append(f"Found {pred_count} prediction statements")
        if abs_count > 0:
            warnings.append(f"Found {abs_count} absolute/unsubstantiated claims")
        if contradiction_count > 0:
            warnings.append(f"Found {contradiction_count} possible contradictions")

        metrics: dict[str, Any] = {
            "prediction_count": pred_count,
            "absolute_claims": abs_count,
            "contradictions": contradiction_count,
        }

        if warnings:
            return HandlerResult(
                decision=HandlerDecision.FAIL,
                detail="; ".join(warnings),
                metrics=metrics,
            )

        return HandlerResult(
            decision=HandlerDecision.PASS,
            detail="No hallucination markers found",
            metrics=metrics,
        )


def pass_result(detail: str) -> HandlerResult:
    """Shortcut for PASS result."""
    return HandlerResult(decision=HandlerDecision.PASS, detail=detail)
