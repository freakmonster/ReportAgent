"""Reviewer node — calls Harness orchestrator, outputs approval decision."""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Run harness governance chain on the generated content.

    Determines: approved / needs_human / rejected based on harness results.

    Args:
        state: Current ReportState with writing.final_content populated.

    Returns:
        Partial state update with review.decision and quality_scores.
    """
    writing: dict[str, Any] = state.get("writing", {})
    base: dict[str, Any] = state.get("base", {})

    final_content = writing.get("final_content", "")

    # ── Run evaluation suite ──────────────────────────────────────────
    try:
        from harness.sensors.eval_suite import evaluate_report
        scores = evaluate_report(final_content)
        quality_scores = scores.to_dict()
    except ImportError:
        quality_scores = {"overall": 0.5}

    # ── Decision logic ────────────────────────────────────────────────
    overall = quality_scores.get("overall", 0.5)
    has_risk = "风险" in final_content

    if overall >= 0.6 and has_risk:
        decision = "approved"
    elif overall >= 0.4:
        decision = "needs_human"
    else:
        decision = "rejected"

    return {
        "review": {
            "stage1_markers": [],
            "stage2_verified": [],
            "quality_scores": quality_scores,
            "hallucination_flag": False,
            "decision": decision,
        },
        "base": {**base, "status": "reviewing"},
    }
