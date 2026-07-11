"""State schemas — collection phase context."""

from __future__ import annotations

from typing import TypedDict


class Document(TypedDict):
    """A collected document from search."""
    title: str
    url: str
    content: str


class CollectionContext(TypedDict):
    """Context for data collection and preprocessing phase."""
    raw_docs: list[Document]
    compressed_summary: dict[str, str]  # chapter_name → summary (≤6K chars each)
    source_urls: list[str]
