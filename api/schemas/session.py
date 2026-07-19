"""Session API schemas for session lifecycle management."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Request body for POST /session/create."""

    user_id: str = Field(..., description="User identifier")
    title: Optional[str] = Field(default=None, description="Session title; auto-generated if not provided")
    first_query: Optional[str] = Field(default=None, description="Optional first query to associate with the session")


class SessionResponse(BaseModel):
    """Response body for session CRUD operations."""

    session_id: str
    user_id: str
    title: str
    status: str
    report_count: int
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """Response body for GET /sessions."""

    sessions: list[SessionResponse]
    total: int
