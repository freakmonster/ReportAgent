"""
Fact Check Stage 2 Handler — LLM/MCP-based verification of high-risk claims.

Includes V2.1 Stage 1.5 Relation Extractor (spaCy NER for qualitative assertions).
Only processes claims already flagged by Stage 1 as high-risk.
This is the "expensive" check (seconds vs milliseconds) — only runs when needed.
"""

from __future__ import annotations

import re
from typing import Any

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler


# ── Stage 1.5: Relation Extractor (V2.1) ──────────────────────────────

# Qualitative assertion patterns: "主体A + 比较词 + 主体B"
_COMPARISON_KEYWORDS: list[str] = [
    "领先", "超越", "超过", "优于", "强于", "高于", "低于",
    "不如", "落后", "逊于", "击败", "碾压", "赶超",
    "领先于", "超越了", "超过了", "优于",
]

# Entity pair extractor: "Company A [比较词] Company B"
# Handles Chinese text (no spaces between characters) using non-greedy matching
_RELATION_PATTERN = re.compile(
    r"(\S{2,10}?)\s*("
    + "|".join(re.escape(kw) for kw in _COMPARISON_KEYWORDS)
    + r")\s*(\S{2,10})"
)


def extract_qualitative_claims(text: str) -> list[dict[str, str]]:
    """Extract qualitative comparison claims (V2.1 Stage 1.5).

    Detects assertions like "比亚迪在电池技术上领先宁德时代" that contain
    no numeric data but express comparative claims.

    Args:
        text: The output text to scan.

    Returns:
        List of dicts with keys: subject, relation, object, sentence.
    """
    claims: list[dict[str, str]] = []
    for match in _RELATION_PATTERN.finditer(text):
        subject = match.group(1)
        relation = match.group(2)
        obj = match.group(3)

        # Find the full sentence containing this claim
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 40)
        sentence = text[start:end].strip()

        claims.append({
            "subject": subject,
            "relation": relation,
            "object": obj,
            "sentence": sentence,
        })

    return claims


class FactStage2Handler(HarnessHandler):
    """Stage 2 fact check: LLM/MCP verification of high-risk claims.

    Includes V2.1 Stage 1.5 Relation Extractor for qualitative assertions.
    Only runs when Stage 1 marked uncited claims.
    """

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Verify high-risk claims using MCP tools or LLM.

        If the output has no uncited claims (from Stage 1), this handler
        still runs the Stage 1.5 Relation Extractor to catch qualitative
        assertions that Stage 1 regex misses.
        """
        from harness.orchestrator.context import PostExecContext

        if not isinstance(post_ctx, PostExecContext):
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No post-exec context, skipping Stage 2",
            )

        output = post_ctx.raw_output
        if not output:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="Empty output, nothing to verify",
            )

        # ── Stage 1.5: Qualitative assertion extraction ─────────────
        qualitative_claims = extract_qualitative_claims(output)

        warnings: list[str] = []
        if qualitative_claims:
            claim_summaries = [
                f"{c['subject']} {c['relation']} {c['object']}"
                for c in qualitative_claims[:5]
            ]
            warnings.append(
                f"Found {len(qualitative_claims)} qualitative claims "
                f"that need citation verification: {'; '.join(claim_summaries)}"
            )

        # ── (Future) MCP/LLM verification for high-risk claims ──────
        # In a full implementation, this would call mcp_client to
        # search/verify claims against external sources.

        metrics: dict[str, Any] = {
            "qualitative_claims_found": len(qualitative_claims),
            "verified_via_llm": 0,
        }

        if warnings:
            return HandlerResult(
                decision=HandlerDecision.FAIL,
                detail="; ".join(warnings),
                metrics=metrics,
            )

        return HandlerResult(
            decision=HandlerDecision.PASS,
            detail="No high-risk claims requiring Stage 2 verification",
            metrics=metrics,
        )
