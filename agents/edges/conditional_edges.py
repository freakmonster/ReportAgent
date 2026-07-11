"""Conditional edge routing — intent, reviewer, and retry routing."""

from __future__ import annotations

from typing import Any


def make_router(node_name: str, routes: dict[str, Any]):
    """Create a LangGraph conditional edge routing function.

    Args:
        node_name: Name of the source node (e.g., 'reviewer', 'intent_classifier').
        routes: Route definitions from YAML template.

    Returns:
        A callable that takes State and returns the next node name.
    """
    def router(state: dict[str, Any]) -> str:
        base = state.get("base", {})

        # ── Reviewer routing ──────────────────────────────────────────
        if node_name == "reviewer":
            review = state.get("review", {})
            decision = review.get("decision", "approved")
            if decision == "approved":
                return routes.get("approved", "publisher")
            if decision == "needs_human":
                return routes.get("needs_human", "human_review")
            if decision == "rejected":
                retry_count = int(base.get("retry_count", 0))
                rejected_route = routes.get("rejected", {})
                if isinstance(rejected_route, dict):
                    if retry_count < 3:
                        return rejected_route.get("true_dest", "writer")
                    return rejected_route.get("false_dest", "human_review")
                return "human_review"

        # ── Intent routing ────────────────────────────────────────────
        if node_name == "intent_classifier":
            intent = base.get("intent", "report")
            if intent == "chat":
                return "chat_response"  # or END in practice
            if intent == "invalid":
                return "invalid_response"
            return "research_planner"  # default → report flow

        # Default: follow routes map
        first_route = list(routes.values())[0] if routes else "END"
        return first_route if isinstance(first_route, str) else "END"

    return router


# ── Standalone routing helpers (used by tests) ────────────────────────

def route_by_intent(state: dict[str, Any]) -> str:
    """Route based on base.intent field."""
    base: dict[str, Any] = state.get("base", {})
    intent = base.get("intent", "report")
    if intent == "report":
        return "research_planner"
    if intent == "chat":
        return "chat_response"
    return "invalid_response"


def route_by_review(state: dict[str, Any]) -> str:
    """Route based on review.decision and base.retry_count."""
    base: dict[str, Any] = state.get("base", {})
    review: dict[str, Any] = state.get("review", {})
    decision = review.get("decision", "approved")
    retry_count = int(base.get("retry_count", 0))

    if decision == "approved":
        return "publisher"
    if decision == "needs_human":
        return "human_review"
    if decision == "rejected":
        if retry_count < 3:
            return "writer"
        return "human_review"
    return "human_review"
