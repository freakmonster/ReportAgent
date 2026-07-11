"""State schemas — nested context for different workflow phases."""

from __future__ import annotations

from typing import TypedDict, Literal


class BaseContext(TypedDict):
    """Metadata that spans the entire workflow lifecycle."""
    workflow_id: str
    user_id: str
    retry_count: int
    version: int          # State version (1=V2.2, 0=V2.0 legacy)
    status: Literal[
        "init", "collecting", "writing", "reviewing",
        "approved", "rejected", "published"
    ]
    template_name: str    # deep_report / flash_news / earnings_analysis
