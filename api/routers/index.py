"""Index build router — triggers async RAG index construction."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.middlewares.auth import auth_dependency

router = APIRouter(tags=["index"])


class IndexBuildRequest(BaseModel):
    """Request body for POST /index/build."""

    collection_name: str = Field(..., min_length=1, description="Target Qdrant collection name")
    documents: list[dict[str, str]] = Field(
        ..., description="List of documents, each with 'url' or 'text' key"
    )


@router.post("/index/build", status_code=202)
async def trigger_index_build(
    req: IndexBuildRequest,
    request: Request,
    user_id: str = Depends(auth_dependency),
) -> dict[str, object]:
    """Trigger an asynchronous index build.

    Each document is enqueued as a separate Redis Stream task. The caller
    can later poll ``GET /index/status/{task_id}`` to check readiness.

    Args:
        req: Collection name + documents to index.

    Returns:
        202 Accepted with task tracking info.
    """
    from infrastructure.message_queue.task_queue import enqueue_indexing_task

    if not req.collection_name:
        raise HTTPException(status_code=400, detail="collection_name is required")
    if not req.documents:
        raise HTTPException(status_code=400, detail="documents list is required")

    # Queue each document as a separate task
    task_ids: list[str] = []
    for doc in req.documents:
        url = doc.get("url", "")
        text = doc.get("text", "")
        if url:
            task_id = await enqueue_indexing_task(
                file_path=url,
                file_type="url",
                collection_name=req.collection_name,
            )
            task_ids.append(task_id)
        elif text:
            task_id = await enqueue_indexing_task(
                file_path=f"text://{text[:100]}",
                file_type="url",
                collection_name=req.collection_name,
            )
            task_ids.append(task_id)

    return {
        "task_ids": task_ids,
        "status": "pending",
        "collection_name": req.collection_name,
    }
