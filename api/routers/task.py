"""Task router — workflow status queries and human review submissions.

V2.1: Double-submit protection via status check (simulated Redis lock + PG optimistic lock).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.request import HumanReviewRequest, TaskStatusRequest
from api.schemas.response import HumanReviewResponse, TaskStatusResponse

router = APIRouter(tags=["task"])

# Simulated in-memory store (production would use PostgreSQL)
_task_store: dict[str, dict[str, str | int]] = {}
_reviewed_workflows: set[str] = set()  # V2.1 double-submit protection


@router.get("/task/{workflow_id}", response_model=TaskStatusResponse)
async def get_task_status(workflow_id: str) -> TaskStatusResponse:
    """Query the current status of a workflow.

    Args:
        workflow_id: The workflow ID to check.

    Returns:
        TaskStatusResponse with current status.
    """
    task = _task_store.get(workflow_id)
    if task is None:
        return TaskStatusResponse(
            workflow_id=workflow_id,
            status="unknown",
            retry_count=0,
            created_at="",
        )
    return TaskStatusResponse(
        workflow_id=workflow_id,
        status=str(task.get("status", "unknown")),
        retry_count=int(task.get("retry_count", 0)),
        created_at=str(task.get("created_at", "")),
    )


@router.post("/task/review", response_model=HumanReviewResponse)
async def submit_human_review(req: HumanReviewRequest) -> HumanReviewResponse:
    """Submit a human review decision for a workflow.

    V2.1 double-submit protection:
    - If the workflow has already been reviewed, return 409 Conflict.
    - This simulates PG optimistic lock: UPDATE WHERE status='pending'.

    Args:
        req: HumanReviewRequest with workflow_id and decision.

    Returns:
        HumanReviewResponse confirming the action.
    """
    # V2.1: Double-submit protection
    if req.workflow_id in _reviewed_workflows:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow {req.workflow_id} has already been reviewed. Duplicate submission detected.",
        )

    _reviewed_workflows.add(req.workflow_id)
    _task_store[req.workflow_id] = {
        "status": req.decision,
        "comment": req.comment or "",
    }

    return HumanReviewResponse(
        workflow_id=req.workflow_id,
        accepted=req.decision == "approved",
        message=f"Review submitted: {req.decision}",
    )
