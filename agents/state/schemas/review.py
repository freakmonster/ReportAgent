"""State schemas — review phase context."""

from __future__ import annotations

from typing import TypedDict


class ClaimMarker(TypedDict):
    """A data claim flagged by Stage 1 fact check."""
    text: str
    entity_type: str
    position: int
    has_citation: bool
    source: str


class VerifiedClaim(TypedDict):
    """A claim verified by Stage 2 fact check."""
    claim_text: str
    verified: bool
    confidence: float
    evidence: str


class ReviewContext(TypedDict):
    """Context for review and verification phase."""
    stage1_markers: list[ClaimMarker]
    stage2_verified: list[VerifiedClaim]
    quality_scores: dict[str, float]   # completeness, accuracy, citation, logic
    hallucination_flag: bool
