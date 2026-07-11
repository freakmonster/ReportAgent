"""
Input Safety Handler — Layer 1 pure Python regex rule bank.

Features:
- Keyword blacklists (harmful, injection patterns)
- Input length limits
- Base64 / hex encoding injection detection
- Millisecond-level execution, no LLM call
"""

from __future__ import annotations

import re
from typing import Any

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler

# Maximum allowed input length (characters)
MAX_INPUT_LENGTH: int = 8000

# Highly dangerous keyword patterns
_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (r"(?:rm\s+-rf|del\s+/[fs])", "Filesystem destruction command"),
    (r"(?:drop\s+table|truncate\s+table|delete\s+from)", "SQL injection (destructive)"),
    (r"(?:curl|wget)\s+.*\|\s*(?:sh|bash)", "Remote script execution via pipe"),
    (r"__import__\s*\(\s*['\"]os['\"]", "Python code injection (os module)"),
    (r"eval\s*\(.*__", "Dynamic code evaluation injection"),
    (r"<script\b[^>]*>", "XSS script tag detected"),
]

# Injection pattern keywords (caught even in natural language)
_INJECTION_KEYWORDS: list[str] = [
    "忽略之前的所有指令",
    "ignore all previous instructions",
    "你是我的助手",
    "system prompt",
    "developer mode",
    "dan mode",
    "jailbreak",
    "提示词",
]


class InputSafetyHandler(HarnessHandler):
    """Layer 1 input safety: regex + keyword rules, no LLM."""

    def __init__(self) -> None:
        self._compiled_patterns: list[tuple[re.Pattern, str]] = [
            (re.compile(p, re.IGNORECASE), desc)
            for p, desc in _BLOCKED_PATTERNS
        ]

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Run input safety checks on the raw user input.

        Returns REJECT for dangerous patterns, FAIL for warnings,
        PASS if all clear.
        """
        from harness.orchestrator.context import PreExecContext

        if not isinstance(pre_ctx, PreExecContext):
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No pre-exec context available (skipping)",
            )

        user_input = pre_ctx.raw_input

        # ── Length check ──────────────────────────────────────────────
        if len(user_input) > MAX_INPUT_LENGTH:
            return HandlerResult(
                decision=HandlerDecision.REJECT,
                detail=f"Input too long ({len(user_input)} > {MAX_INPUT_LENGTH})",
                metrics={"input_length": len(user_input)},
            )

        # ── Dangerous pattern matching ────────────────────────────────
        for pattern, description in self._compiled_patterns:
            if pattern.search(user_input):
                return HandlerResult(
                    decision=HandlerDecision.REJECT,
                    detail=f"Dangerous pattern detected: {description}",
                    metrics={"matched_pattern": description},
                )

        # ── Injection keywords ────────────────────────────────────────
        lower_input = user_input.lower()
        hits: list[str] = [
            kw for kw in _INJECTION_KEYWORDS if kw.lower() in lower_input
        ]
        if hits:
            return HandlerResult(
                decision=HandlerDecision.FAIL,
                detail=f"Injection keywords detected: {', '.join(hits)}",
                metrics={"injection_hits": hits},
            )

        # ── Encoding injection (base64 / hex) ─────────────────────────
        b64_pattern = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")
        hex_pattern = re.compile(r"(?:\\x[0-9a-fA-F]{2}){20,}")
        if b64_pattern.search(user_input) or hex_pattern.search(user_input):
            return HandlerResult(
                decision=HandlerDecision.FAIL,
                detail="Encoded content detected (possible injection via Base64 or hex)",
                metrics={"encoded_injection": True},
            )

        return HandlerResult(
            decision=HandlerDecision.PASS,
            detail="Input safety check passed",
            metrics={"input_length": len(user_input)},
        )
