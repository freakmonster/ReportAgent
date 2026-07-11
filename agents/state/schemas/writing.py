"""State schemas — writing phase context."""

from __future__ import annotations

from typing import TypedDict


class WritingContext(TypedDict):
    """Context for writing and editing phase."""
    chapter_drafts: dict[str, str]   # chapter_name → draft content
    final_content: str
    citation_list: list[str]
