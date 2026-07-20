"""
Structural Handler — output schema validation, style check, safety filter.

Validates that node output conforms to expected structure, removes
potentially dangerous content, and flags style issues.
"""

from __future__ import annotations

from typing import Any

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler


class StructuralHandler(HarnessHandler):
    """Validates output structure, style, and content safety."""

    # Content that should not appear in final output
    _BLACKLIST_STRINGS: list[str] = [
        "<script",
        "</script",
        "javascript:",
        "onerror=",
        "onload=",
    ]

    # Style issues to warn about
    _STYLE_PATTERNS: list[tuple[str, str]] = [
        ("　", "Full-width space (replace with normal space)"),
        ("\r\n", "Windows line endings (use \\n)"),
    ]

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Run structural validation on node output.

        Returns REJECT if blacklisted content found, FAIL for style issues,
        PASS if all clear.
        """
        from harness.orchestrator.context import PostExecContext

        if not isinstance(post_ctx, PostExecContext):
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No post-exec context, skipping structural check",
            )

        output = post_ctx.raw_output
        if not output:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="Empty output, no structural issues",
            )

        # ── Blacklist check ───────────────────────────────────────────
        output_lower = output.lower()
        blacklist_hits: list[str] = []
        for blacklisted in self._BLACKLIST_STRINGS:
            if blacklisted.lower() in output_lower:
                blacklist_hits.append(blacklisted)

        if blacklist_hits:
            return HandlerResult(
                decision=HandlerDecision.REJECT,
                detail=f"Blacklisted content detected: {', '.join(blacklist_hits)}",
                metrics={"blacklist_hits": blacklist_hits},
            )

        # ── Style check ───────────────────────────────────────────────
        style_warnings: list[str] = []
        for pattern, description in self._STYLE_PATTERNS:
            if pattern in output:
                style_warnings.append(description)

        # ── Length check ──────────────────────────────────────────────
        metrics: dict[str, Any] = {"output_length": len(output)}

        if len(output) < 10 and post_ctx.node_name not in ("intent_classifier",):
            style_warnings.append("Output is unusually short (< 10 chars)")

        if style_warnings:
            return HandlerResult(
                decision=HandlerDecision.FAIL,
                detail=f"Style warnings: {'; '.join(style_warnings)}",
                metrics=metrics,
            )

        return HandlerResult(
            decision=HandlerDecision.PASS,
            detail="Structural check passed",
            metrics=metrics,
        )
