"""State schemas — nested context for different workflow phases."""

from __future__ import annotations

from typing import Literal, TypedDict


class BaseContext(TypedDict):
    """Metadata that spans the entire workflow lifecycle."""
    workflow_id: str
    user_id: str
    session_id: str       # Session identifier for short-term memory association
    tenant_id: str        # Multi-tenant isolation identifier (default: "default")
    retry_count: int
    version: int          # State version (1=V2.2, 0=V2.0 legacy)
    status: Literal[
        "init", "collecting", "writing", "reviewing",
        "approved", "rejected", "published"
    ]
    template_name: str    # deep_report / flash_news / earnings_analysis
    model: str            # deepseek-flash / deepseek-pro / qwen-8b / qwen-32b / qwen-max
