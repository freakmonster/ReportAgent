"""Human review node — interrupt point for manual approval.

In production, this would:
- Persist full state to PostgreSQL via LangGraph Checkpointer
- Set Redis signal: SET human_review:{workflow_id} PENDING EX 3600
- Send email notification via MCP

Currently returns a simulated approval for testing.
"""

from __future__ import annotations

from typing import Any


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Simulate human review (always approves for now).

    Args:
        state: Current ReportState.

    Returns:
        Partial state update.
    """
    review: dict[str, Any] = state.get("review", {})
    base: dict[str, Any] = state.get("base", {})

    # Simulated human approval
    review["decision"] = "approved"

    return {
        "review": review,
        "base": {**base, "status": "reviewing"},
    }
