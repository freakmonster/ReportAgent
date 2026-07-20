"""Session router — session lifecycle management.

Endpoints:
- POST /session/create       — create a new session
- GET  /sessions             — list sessions for a user
- DELETE /session/{session_id} — soft-delete a session + clear Redis memory
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from api.schemas.session import (
    CreateSessionRequest,
    SessionListResponse,
    SessionResponse,
)
from infrastructure.database.repositories.session_repo import get_session_repo
from infrastructure.memory.short_term import delete_memory

router = APIRouter(prefix="/session", tags=["session"])


def _record_to_response(record) -> SessionResponse:
    """Convert a SessionRecord to SessionResponse."""
    return SessionResponse(
        session_id=record.session_id,
        user_id=record.user_id,
        title=record.title or "未命名会话",
        status=record.status,
        report_count=record.report_count,
        created_at=record.created_at.isoformat() if record.created_at else "",
        updated_at=record.updated_at.isoformat() if record.updated_at else "",
    )


@router.post("/create", response_model=SessionResponse)
async def create_session(body: CreateSessionRequest) -> SessionResponse:
    """Create a new session.

    Generates a UUID for session_id.  If no title is provided, defaults to
    "未命名会话".
    """
    repo = get_session_repo()

    session_id = str(uuid.uuid4())
    title = body.title if body.title else "未命名会话"

    record = await repo.create(
        session_id=session_id,
        user_id=body.user_id,
        title=title,
        first_query=body.first_query,
    )

    return _record_to_response(record)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: str = Query(..., description="User identifier"),
) -> SessionListResponse:
    """List all active sessions for a user, ordered by most recent update."""
    repo = get_session_repo()

    records = await repo.list_by_user(user_id)

    sessions = [_record_to_response(r) for r in records]
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.delete("/session/{session_id}", response_model=SessionResponse)
async def delete_session(
    session_id: str,
    user_id: str = Query(..., description="User identifier for auth matching"),
) -> SessionResponse:
    """Soft-delete a session and clear its Redis short-term memory.

    Verifies that the session belongs to the given user before deleting.
    """
    repo = get_session_repo()

    # Auth check: verify the session belongs to this user
    record = await repo.get_by_id(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this user")

    # Capture response before deletion
    response = _record_to_response(record)

    # Soft-delete in PostgreSQL
    await repo.soft_delete(session_id)

    # Clean up Redis short-term memory (best-effort, ignore errors)
    try:
        await delete_memory(user_id, session_id)
    except Exception:
        pass

    return response
