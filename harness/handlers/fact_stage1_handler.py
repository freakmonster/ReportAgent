"""
Fact Check Stage 1 Handler — regex-based data entity extraction.

Identifies:
- Numeric data (percentages, counts, monetary values)
- Dates / time ranges
- Ratios and proportions

Marks claims that lack source citations.  Executes in milliseconds, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler


@dataclass
class DataClaim:
    """A data entity found in the text."""

    text: str  # The matched substring
    entity_type: str  # "percentage", "count", "date", "ratio", "currency"
    position: int = 0  # Character position in the output
    has_citation: bool = False  # Whether a citation follows this claim
    source: str = ""  # Citation text if found


# ── Entity extraction patterns ────────────────────────────────────────

_PERCENTAGE_RE = re.compile(r"(\d+\.?\d*)\s*%")
_COUNT_RE = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万|亿|千|百万|千万|辆|台|家|人|份)")
_MONEY_RE = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:元|美元|欧元|港元|日元|万元|亿元)")
_DATE_RANGE_RE = re.compile(r"(\d{4})\s*(?:年|Q[1-4]|月|季度)")
_RATIO_RE = re.compile(r"(\d+\.?\d*)\s*(?::|：)\s*(\d+\.?\d*)")
_GROWTH_RE = re.compile(r"(?:增长|下降|同比|环比|增速)\s*(\d+\.?\d*)\s*%")

# Citation pattern — looks for [N], [N,M], [N-M] right after a claim
_CITATION_RE = re.compile(r"\[\d+(?:[,，\-]\d+)?\]")


def extract_data_claims(text: str) -> list[DataClaim]:
    """Extract data claims from text using regex patterns.

    Args:
        text: The output text to analyze.

    Returns:
        List of DataClaim objects extracted from the text.
    """
    claims: list[DataClaim] = []

    for pattern, entity_type in [
        (_PERCENTAGE_RE, "percentage"),
        (_MONEY_RE, "currency"),
        (_COUNT_RE, "count"),
        (_RATIO_RE, "ratio"),
        (_GROWTH_RE, "growth_rate"),
        (_DATE_RANGE_RE, "date"),
    ]:
        for match in pattern.finditer(text):
            claim_text = match.group(0)
            pos = match.start()

            # Check if this claim has a citation nearby (within 50 chars after)
            post_text = text[pos + len(claim_text) : pos + len(claim_text) + 50]
            citation_match = _CITATION_RE.search(post_text)
            has_citation = citation_match is not None
            source = citation_match.group(0) if citation_match else ""

            claims.append(
                DataClaim(
                    text=claim_text,
                    entity_type=entity_type,
                    position=pos,
                    has_citation=has_citation,
                    source=source,
                )
            )

    return claims


class FactStage1Handler(HarnessHandler):
    """Stage 1 fact check: regex extraction, no LLM, ms-level."""

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Extract data claims from node output and mark uncited ones."""
        from harness.orchestrator.context import PostExecContext

        if not isinstance(post_ctx, PostExecContext):
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No post-exec context, skipping Stage 1",
            )

        output = post_ctx.raw_output
        if not output:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="Empty output, no claims to check",
            )

        claims = extract_data_claims(output)
        total = len(claims)
        uncited = sum(1 for c in claims if not c.has_citation)

        if total == 0:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No data entities found",
                metrics={"total_claims": 0},
            )

        uncited_claims_data: list[dict[str, Any]] = [
            {"text": c.text, "type": c.entity_type, "pos": c.position}
            for c in claims
            if not c.has_citation
        ]

        if uncited > 0:
            return HandlerResult(
                decision=HandlerDecision.FAIL,
                detail=f"{uncited}/{total} data claims lack citations",
                metrics={
                    "total_claims": total,
                    "uncited_claims": uncited,
                    "citation_rate": round((total - uncited) / total, 2) if total else 0,
                    "uncited_list": uncited_claims_data[:10],
                },
            )

        return HandlerResult(
            decision=HandlerDecision.PASS,
            detail=f"All {total} data claims have citations",
            metrics={"total_claims": total, "citation_rate": 1.0},
        )
