"""Human review node — real interrupt with PostgreSQL + Redis persistence.

In production:
1. Persists full state to PostgreSQL via LangGraph Checkpointer (automatic)
2. Writes workflow status to workflow_states table (status='pending')
3. Sets Redis signal: SET human_review:{workflow_id} PENDING EX 3600
4. Sends email notification via MCP (graceful degradation)
5. Pauses execution via ``interrupt()`` until POST /review/{workflow_id} callback
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Real human review interrupt with observability.

    Behaviour by ``review.decision``:

    - **approved**: No interrupt. Log and return state unchanged.
      The reviewer already approved this output.

    - **rejected**: No interrupt. Log rejection and return state.
      The conditional_edges router will direct to ``rejected`` path.

    - **needs_human** (default): Interrupt.
      1. Write status='pending' to workflow_states table (via db session)
      2. Set Redis signal ``human_review:{workflow_id} PENDING EX 3600``
      3. Send MCP Email notification (best-effort, not blocking)
      4. Call ``interrupt("Waiting for human review")`` to pause the graph
      5. When resumed, state has already been updated by task.py

    Args:
        state: Current ReportState.

    Returns:
        Partial state update (or pauses via interrupt).
    """
    from langgraph.types import interrupt

    review: dict[str, Any] = state.get("review", {})
    base: dict[str, Any] = state.get("base", {})

    workflow_id: str = base.get("workflow_id", "unknown")
    user_input: str = base.get("user_input", "")
    incoming_decision: str = review.get("decision", "needs_human")
    quality_scores: dict[str, float] = review.get("quality_scores", {})

    # ── decisions that don't need human review ────────────────────────
    if incoming_decision == "approved":
        logger.info(
            "Human review bypass (auto-approved) | workflow=%s | score=%.2f",
            workflow_id,
            quality_scores.get("overall", -1),
        )
        review["human_review_status"] = "bypassed"
        review["review_feedback"] = review.get("review_feedback", "")
        return {
            "review": review,
            "base": {**base, "status": "reviewing"},
        }

    if incoming_decision == "rejected":
        logger.info(
            "Human review bypass (rejected) | workflow=%s",
            workflow_id,
        )
        review["human_review_status"] = "bypassed"
        review["review_feedback"] = review.get(
            "review_feedback", "Content rejected by reviewer"
        )
        return {
            "review": review,
            "base": {**base, "status": "reviewing"},
        }

    # ── needs_human — persist, notify, interrupt ──────────────────────
    logger.info(
        "Human review pending | workflow=%s | input=%s",
        workflow_id,
        user_input[:120],
    )

    # 1. Persist workflow status to workflow_states table
    try:
        from datetime import datetime

        from infrastructure.database.repositories.workflow_repo import (
            WorkflowStateRecord,
            get_workflow_repo,
        )

        record = WorkflowStateRecord(
            workflow_id=workflow_id,
            status="pending",
            state_data=state,
            user_id=base.get("user_id", ""),
            template_name=base.get("template_name", ""),
            retry_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        repo = get_workflow_repo()
        await repo.save(record)
        logger.info(
            "human_review.state_saved | workflow=%s",
            workflow_id,
        )
    except Exception as exc:
        logger.warning(
            "human_review.state_save_failed | workflow=%s | %s",
            workflow_id, exc,
        )

    # 2. Set Redis signal
    try:
        from infrastructure.cache.redis_client import get_redis

        redis = get_redis()
        await redis.set(f"human_review:{workflow_id}", "PENDING", ex=3600)
        logger.info(
            "human_review.redis_signal | workflow=%s",
            workflow_id,
        )
    except Exception as exc:
        logger.warning(
            "human_review.redis_failed | workflow=%s | %s",
            workflow_id, exc,
        )

    # 3. MCP Email notification (best-effort)
    try:
        from mcp_tools.mcp_client import call_mcp_tool

        await call_mcp_tool("mcp_send_email", {
            "to": "admin@example.com",
            "subject": f"Human Review Required: {workflow_id}",
            "body": (
                f"Workflow {workflow_id} requires human review.\n\n"
                f"Query: {user_input}\n"
                f"Quality scores: {quality_scores}\n\n"
                f"Review at: /task/review/{workflow_id}"
            ),
        })
        logger.info("human_review.email_sent | workflow=%s", workflow_id)
    except Exception as exc:
        logger.info(
            "human_review.email_skipped | workflow=%s | %s",
            workflow_id, exc,
        )

    # 4. Interrupt — wait for external callback
    interrupt("Waiting for human review")

    # After resume: state already updated with review decision
    review["human_review_status"] = review.get("human_review_status", "resumed")
    return {
        "review": review,
        "base": {**base, "status": "reviewing"},
    }
