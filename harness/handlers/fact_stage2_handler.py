"""
Fact Check Stage 2 Handler — LLM/MCP-based verification of high-risk claims.

Stage 1.5 (qualitative assertion extraction) runs first, then Stage 2 verifies
each flagged claim against external sources via MCP web_search or LLM evaluation.

Only processes claims already flagged by Stage 1 as high-risk.
This is the "expensive" check (seconds vs milliseconds) — only runs when needed.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler

# ── Stage 1.5: Relation Extractor (V2.1) ──────────────────────────────

_COMPARISON_KEYWORDS: list[str] = [
    "领先", "超越", "超过", "优于", "强于", "高于", "低于",
    "不如", "落后", "逊于", "击败", "碾压", "赶超",
    "领先于", "超越了", "超过了", "优于",
]

_RELATION_PATTERN = re.compile(
    r"(\S{2,30}?)\s*("
    + "|".join(re.escape(kw) for kw in _COMPARISON_KEYWORDS)
    + r")\s*([\u4e00-\u9fff\w\-\.]{2,20})"
)

# Maximum claims to verify per invocation (cost control)
_MAX_CLAIMS_TO_VERIFY = 5


def extract_qualitative_claims(text: str) -> list[dict[str, str]]:
    """Extract qualitative comparison claims (V2.1 Stage 1.5)."""
    claims: list[dict[str, str]] = []
    for match in _RELATION_PATTERN.finditer(text):
        subject = match.group(1)
        relation = match.group(2)
        obj = match.group(3)
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


# ── Stage 2: External verification ────────────────────────────────────

async def _verify_claim_via_mcp(claim: dict[str, str]) -> dict[str, Any]:
    """Verify a single claim using MCP web_search.

    Args:
        claim: Dict with subject, relation, object, sentence keys.

    Returns:
        Dict with verified (bool), evidence (str), and method (str).
    """
    query = f"{claim['subject']} {claim['relation']} {claim['object']}"

    try:
        from mcp_tools.mcp_client import mcp_client
        from config.settings import settings

        search_url = getattr(settings, "mcp_search_url", "")
        if not search_url:
            return {"verified": False, "evidence": "", "method": "mcp_unavailable"}

        result = await mcp_client.call(
            server_url=search_url,
            tool_name="web_search",
            arguments={"query": query, "max_results": 3},
            server_name="search",
        )

        if not result.success:
            return {"verified": False, "evidence": "", "method": "mcp_error"}

        # Check if search results contain evidence
        evidence_text = ""
        results = result.data.get("results", []) if isinstance(result.data, dict) else []
        for r in results[:3]:
            snippet = r.get("snippet", "") if isinstance(r, dict) else str(r)
            evidence_text += snippet + " "

        # Simple heuristic: evidence contains both entities
        verified = (
            claim["subject"] in evidence_text
            and claim["object"] in evidence_text
        )

        return {
            "verified": verified,
            "evidence": evidence_text[:500],
            "method": "mcp_web_search",
        }

    except Exception:
        return {"verified": False, "evidence": "", "method": "mcp_exception"}


async def _verify_claim_via_llm(claim: dict[str, str]) -> dict[str, Any]:
    """Verify a claim using LLM evaluation (fallback when MCP unavailable).

    Args:
        claim: Dict with subject, relation, object, sentence keys.

    Returns:
        Dict with verified (bool), evidence (str), and method (str).
    """
    prompt = (
        f"请判断以下陈述的真实性。陈述：「{claim['sentence']}」\n"
        f"主体：{claim['subject']}\n"
        f"关系：{claim['relation']}\n"
        f"对象：{claim['object']}\n\n"
        f"请回复 JSON：{{\"verified\": true/false, \"reason\": \"简短理由\"}}\n"
        f"如果你不确定，请回复 verified: false。只返回 JSON。"
    )

    try:
        from models.llm_providers.deepseek_client import DeepSeekClient

        client = DeepSeekClient()
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )

        content = response.choices[0].message.content if response.choices else ""

        # Parse JSON from response
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return {
                "verified": parsed.get("verified", False),
                "evidence": parsed.get("reason", ""),
                "method": "llm_evaluation",
            }

        return {"verified": False, "evidence": content[:200], "method": "llm_unparseable"}

    except Exception as exc:
        return {"verified": False, "evidence": str(exc)[:200], "method": "llm_exception"}


async def _verify_claims(claims: list[dict[str, str]]) -> dict[str, Any]:
    """Verify a batch of claims, trying MCP first then LLM fallback.

    Args:
        claims: List of claim dicts to verify.

    Returns:
        Dict with verified_count, unverified_count, details list.
    """
    to_verify = claims[:_MAX_CLAIMS_TO_VERIFY]
    verified_count = 0
    unverified_count = 0
    details: list[dict[str, Any]] = []

    for claim in to_verify:
        # Try MCP first
        result = await _verify_claim_via_mcp(claim)

        # Fallback to LLM if MCP didn't verify
        if not result["verified"]:
            llm_result = await _verify_claim_via_llm(claim)
            if llm_result["verified"]:
                result = llm_result

        if result["verified"]:
            verified_count += 1
        else:
            unverified_count += 1

        details.append({
            "claim": f"{claim['subject']} {claim['relation']} {claim['object']}",
            "verified": result["verified"],
            "method": result["method"],
            "evidence": result["evidence"][:200],
        })

    return {
        "verified_count": verified_count,
        "unverified_count": unverified_count,
        "total_checked": len(to_verify),
        "total_found": len(claims),
        "details": details,
    }


# ── Handler ───────────────────────────────────────────────────────────

class FactStage2Handler(HarnessHandler):
    """Stage 2 fact check: MCP/LLM verification of high-risk claims.

    Stage 1.5 (qualitative assertion extraction) runs inline.
    Stage 2 verifies flagged claims against external sources.
    Only runs when Stage 1 marked uncited claims.
    """

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Verify high-risk claims using MCP tools or LLM.

        Args:
            pre_ctx: PreExecContext (unused in Stage 2).
            post_ctx: PostExecContext with raw_output.

        Returns:
            HandlerResult with verification results.
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

        if not qualitative_claims:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No qualitative claims requiring Stage 2 verification",
                metrics={"qualitative_claims_found": 0},
            )

        # ── Stage 2: External verification ──────────────────────────
        verification = await _verify_claims(qualitative_claims)

        unverified = verification["unverified_count"]
        total = verification["total_checked"]

        detail_parts: list[str] = []
        for d in verification["details"]:
            status = "✓" if d["verified"] else "✗"
            detail_parts.append(
                f"{status} {d['claim']} [{d['method']}]"
            )

        if unverified == 0:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail=f"All {total} qualitative claims verified: " + "; ".join(detail_parts),
                metrics={
                    "qualitative_claims_found": len(qualitative_claims),
                    "verified_via_mcp": verification["verified_count"],
                    "unverified": unverified,
                    "details": verification["details"],
                },
            )

        # Some claims unverified → warning
        return HandlerResult(
            decision=HandlerDecision.FAIL,
            detail=f"{unverified}/{total} qualitative claims unverified: " + "; ".join(detail_parts),
            metrics={
                "qualitative_claims_found": len(qualitative_claims),
                "verified_via_mcp": verification["verified_count"],
                "unverified_via_mcp": unverified,
                "unverified_via_llm": unverified,
                "details": verification["details"],
            },
        )
