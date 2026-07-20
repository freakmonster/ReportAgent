"""
Pydantic request models for the API layer.

Validates incoming requests before they reach routers.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# ── Chat request ──────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """SSE chat / report generation request."""

    query: str = Field(
        ..., min_length=1, max_length=5000, description="User query for report generation"
    )
    report_type: str = Field(
        default="deep_report",
        pattern=r"^(deep_report|flash_news|earnings_analysis)$",
        description="Report template type",
    )
    model: str = Field(
        default="deepseek-flash",
        pattern=r"^(deepseek-flash|deepseek-pro|qwen-8b|qwen-32b|qwen-max)$",
        description="LLM model selection: deepseek-flash, deepseek-pro, qwen-8b, qwen-32b, qwen-max",
    )
    user_id: str = Field(
        default="anonymous", description="User identifier for rate limiting and personalization"
    )
    session_id: Optional[str] = Field(
        default=None, description="Session identifier for short-term memory association"
    )
    conversation_id: Optional[str] = Field(
        default=None, description="Optional conversation ID for multi-turn"
    )
    reconnect_token: Optional[str] = Field(
        default=None, description="SSE reconnect token for zombie workflow recovery"
    )


# ── Human review request ──────────────────────────────────────────────


class HumanReviewRequest(BaseModel):
    """Submit a human review decision."""

    workflow_id: str = Field(..., description="Workflow ID to review")
    decision: str = Field(
        ..., pattern=r"^(approved|rejected|needs_changes)$", description="Review decision"
    )
    comment: Optional[str] = Field(
        default=None, max_length=1000, description="Optional reviewer comment"
    )


# ── Task status request ───────────────────────────────────────────────


class TaskStatusRequest(BaseModel):
    """Query the status of a workflow."""

    workflow_id: str = Field(..., description="Workflow ID to query")
