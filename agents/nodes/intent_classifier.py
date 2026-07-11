"""Intent classifier node — classify user input as report/chat/invalid.

Uses services.intent_service for classification.
Merges with deep injection detection (V2.0).
Identifies report_type → template_name for V2.2 dynamic routing.
"""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Classify user intent and set routing fields in base context.

    Reads: base.user_input (the raw query from the user)
    Sets:  base.intent, base.template_name

    Args:
        state: Current ReportState.

    Returns:
        Partial state update.
    """
    from services.intent_service import classify_intent

    base: dict[str, Any] = state.get("base", {})
    user_input = base.get("user_input", "")

    result = classify_intent(user_input)

    template_name = result.report_type or "deep_report"

    return {
        "base": {
            **base,
            "intent": result.category.value,
            "template_name": template_name,
            "confidence": result.confidence,
        },
    }
