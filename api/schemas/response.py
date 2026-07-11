"""
Pydantic response models with unified error codes.

Error codes:
- 4001: Invalid input (Harness rejected)
- 4002: Permission denied
- 4003: Rate limit triggered
- 5001: Agent execution failed
- 5002: MCP tool call failed (degraded)
- 5003: Human review timeout
- 5004: Model circuit breaker open (degrading)
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response with dependency status."""
    status: str = "ok"
    services: dict[str, str] = Field(default_factory=dict)
    version: str = "0.1.0"


class ErrorResponse(BaseModel):
    """Unified error response format."""
    error: bool = True
    code: int = Field(..., description="Error code (4001-5004)")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(default=None, description="Technical detail")


class TaskStatusResponse(BaseModel):
    """Workflow task status."""
    workflow_id: str
    status: str  # init/collecting/writing/reviewing/approved/rejected/published
    retry_count: int = 0
    created_at: str = ""


class HumanReviewResponse(BaseModel):
    """Human review submission result."""
    workflow_id: str
    accepted: bool
    message: str = ""


class ChatProgressEvent(BaseModel):
    """SSE event for real-time workflow progress."""
    event: str = "progress"  # progress / complete / error
    node: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""
