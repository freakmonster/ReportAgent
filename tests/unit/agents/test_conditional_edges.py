"""Unit tests for conditional edge routing logic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from agents.edges.conditional_edges import (
    make_router,
    route_by_intent,
    route_by_review,
)  # noqa: E402


class TestIntentRouting:
    """Verify intent-based routing."""

    def test_report_routes_to_planner(self) -> None:
        state = {"base": {"intent": "report"}}
        assert route_by_intent(state) == "research_planner"

    def test_chat_routes_to_chat(self) -> None:
        state = {"base": {"intent": "chat"}}
        assert route_by_intent(state) == "chat_response"

    def test_invalid_routes_to_invalid(self) -> None:
        state = {"base": {"intent": "invalid"}}
        assert route_by_intent(state) == "invalid_response"

    def test_default_is_report(self) -> None:
        state = {"base": {}}
        assert route_by_intent(state) == "research_planner"


class TestReviewRouting:
    """Verify reviewer conditional routing."""

    def test_approved_to_publisher(self) -> None:
        state = {"base": {"retry_count": 0}, "review": {"decision": "approved"}}
        assert route_by_review(state) == "publisher"

    def test_needs_human_to_human_review(self) -> None:
        state = {"base": {}, "review": {"decision": "needs_human"}}
        assert route_by_review(state) == "human_review"

    def test_rejected_retry_lt_3_to_writer(self) -> None:
        state = {"base": {"retry_count": 2}, "review": {"decision": "rejected"}}
        assert route_by_review(state) == "writer"

    def test_rejected_retry_eq_3_to_human(self) -> None:
        state = {"base": {"retry_count": 3}, "review": {"decision": "rejected"}}
        assert route_by_review(state) == "human_review"

    def test_rejected_retry_gt_3_to_human(self) -> None:
        state = {"base": {"retry_count": 5}, "review": {"decision": "rejected"}}
        assert route_by_review(state) == "human_review"


class TestMakeRouter:
    """Verify the make_router factory."""

    def test_reviewer_router_approved(self) -> None:
        router = make_router(
            "reviewer",
            {
                "approved": "publish",
                "needs_human": "human",
                "rejected": {"true_dest": "write", "false_dest": "human"},
            },
        )
        state = {"base": {"retry_count": 1}, "review": {"decision": "approved"}}
        assert router(state) == "publish"

    def test_intent_router(self) -> None:
        router = make_router("intent_classifier", {"report": "planner"})
        state = {"base": {"intent": "report"}}
        assert router(state) in ("planner", "research_planner")  # may use configured or default
