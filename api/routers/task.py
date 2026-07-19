"""Task router — workflow status queries and human review submissions.

V2.3: PostgreSQL-backed with optimistic locking and graph resume.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api.middlewares.auth import auth_dependency
from api.schemas.request import HumanReviewRequest, TaskStatusRequest
from api.schemas.response import HumanReviewResponse, TaskStatusResponse

router = APIRouter(tags=["task"])


@router.get("/task/{workflow_id}", response_model=TaskStatusResponse)
async def get_task_status(
    workflow_id: str,
    request: Request,
    user_id: str = Depends(auth_dependency),
) -> TaskStatusResponse:
    """Query the current status of a workflow from PostgreSQL.

    Args:
        workflow_id: The workflow ID to check.

    Returns:
        TaskStatusResponse with current status.
    """
    try:
        from infrastructure.database.repositories.workflow_repo import (
            get_workflow_repo,
        )

        repo = get_workflow_repo()
        record = await repo.get_by_id(workflow_id)
        if record is None:
            return TaskStatusResponse(
                workflow_id=workflow_id,
                status="unknown",
                retry_count=0,
                created_at="",
            )
        return TaskStatusResponse(
            workflow_id=workflow_id,
            status=record.status,
            retry_count=record.retry_count,
            created_at=record.created_at.isoformat(),
        )
    except Exception:
        return TaskStatusResponse(
            workflow_id=workflow_id,
            status="unknown",
            retry_count=0,
            created_at="",
        )


@router.post("/task/review", response_model=HumanReviewResponse)
async def submit_human_review(
    req: HumanReviewRequest,
    request: Request,
    user_id: str = Depends(auth_dependency),
) -> HumanReviewResponse:
    """Submit a human review decision for a paused workflow.

    Uses optimistic locking (``approve_with_lock`` / ``reject_with_lock``)
    to prevent double-submission, then resumes the LangGraph workflow via
    ``graph.aupdate_state()`` + ``astream(None)``.

    Args:
        req: HumanReviewRequest with workflow_id and decision.

    Returns:
        HumanReviewResponse confirming the action.
    """
    from agents.state import ReportState
    from agents.workflows.builder import WorkflowBuilder
    from infrastructure.database.repositories.workflow_repo import (
        get_workflow_repo,
    )

    workflow_id = req.workflow_id
    decision = req.decision
    checkpointer = getattr(request.app.state, "checkpointer", None)

    if checkpointer is None:
        raise HTTPException(
            status_code=503,
            detail="Checkpointer not available. Cannot resume workflow.",
        )

    # ── 1. Optimistic lock ────────────────────────────────────────────
    repo = get_workflow_repo()

    if decision == "approved":
        locked = await repo.approve_with_lock(workflow_id)
    elif decision in ("rejected", "needs_changes"):
        locked = await repo.reject_with_lock(workflow_id, reason=req.comment or decision)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {decision}")

    if not locked:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow {workflow_id} has already been reviewed. Duplicate submission detected.",
        )

    # ── 2. Query template_name ────────────────────────────────────────
    record = await repo.get_by_id(workflow_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    template_name = record.template_name

    # ── 3. Build graph with checkpointer ──────────────────────────────
    builder = WorkflowBuilder()
    harness = getattr(request.app.state, "harness_orchestrator", None)
    graph = builder.build(
        template_name,
        ReportState,
        harness_orchestrator=harness,
        checkpointer=checkpointer,
    )

    thread_config = {"configurable": {"thread_id": workflow_id}}

    # ── 4. Update state with review decision ──────────────────────────
    await graph.aupdate_state(
        thread_config,
        {"review": {"decision": decision}},
    )

    # ── 5. Resume execution ──────────────────────────────────────────
    try:
        async for _ in graph.astream(None, config=thread_config, stream_mode="updates"):
            pass  # Consume remaining node outputs
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume workflow: {exc}",
        )

    return HumanReviewResponse(
        workflow_id=workflow_id,
        accepted=decision == "approved",
        message=f"Review submitted: {decision}",
    )
