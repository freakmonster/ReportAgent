"""State migrator — upgrade V2.0 legacy state to V2.2 nested format."""

from __future__ import annotations

from typing import Any

from agents.state import ReportState
from agents.state.schemas.base import BaseContext
from agents.state.schemas.collection import CollectionContext, Document
from agents.state.schemas.review import ClaimMarker, ReviewContext, VerifiedClaim
from agents.state.schemas.writing import WritingContext


def upgrade_v1_to_v2(old_state: dict[str, Any]) -> ReportState:
    """Migrate a V2.0 flat state dict to V2.2 nested ReportState.

    V2.0 used a single TypedDict with all fields flat.
    V2.2 splits them into base/collection/writing/review sub-contexts.

    Args:
        old_state: Flat dict from V2.0 format.

    Returns:
        Migrated ReportState with nested structure.
    """
    # ── Base context ──────────────────────────────────────────────────
    base = BaseContext(
        workflow_id=str(old_state.get("workflow_id", "")),
        user_id=str(old_state.get("user_id", "")),
        retry_count=int(old_state.get("retry_count", 0)),
        version=1,
        status=safe_status(old_state.get("status", "init")),
        template_name=str(old_state.get("template_name", "deep_report")),
    )

    # ── Collection context ────────────────────────────────────────────
    raw_docs_raw: list[dict[str, Any]] = old_state.get("raw_docs", []) or []
    raw_docs: list[Document] = [
        Document(
            title=str(d.get("title", "")),
            url=str(d.get("url", "")),
            content=str(d.get("content", "")),
        )
        for d in raw_docs_raw
    ]
    compressed_raw: dict[str, Any] = old_state.get("compressed_summary", {}) or {}
    source_urls_raw: list[str] = old_state.get("source_urls", []) or []
    source_urls = [str(u) for u in source_urls_raw]

    analysis: dict[str, Any] = old_state.get("analysis", {}) or {}

    collection = CollectionContext(
        raw_docs=raw_docs,
        compressed_summary={str(k): str(v) for k, v in compressed_raw.items()},
        source_urls=source_urls,
        analysis=analysis,
    )

    # ── Writing context ───────────────────────────────────────────────
    drafts_raw: dict[str, Any] = old_state.get("chapter_drafts", {}) or {}
    writing = WritingContext(
        chapter_drafts={str(k): str(v) for k, v in drafts_raw.items()},
        final_content=str(old_state.get("final_content", "")),
        citation_list=[str(c) for c in (old_state.get("citation_list", []) or [])],
    )

    # ── Review context ────────────────────────────────────────────────
    markers_raw: list[dict[str, Any]] = old_state.get("stage1_markers", []) or []
    stage1_markers: list[ClaimMarker] = [
        ClaimMarker(
            text=str(m.get("text", "")),
            entity_type=str(m.get("entity_type", "")),
            position=int(m.get("position", 0)),
            has_citation=bool(m.get("has_citation", False)),
            source=str(m.get("source", "")),
        )
        for m in markers_raw
    ]
    verified_raw: list[dict[str, Any]] = old_state.get("stage2_verified", []) or []
    stage2_verified: list[VerifiedClaim] = [
        VerifiedClaim(
            claim_text=str(v.get("claim_text", "")),
            verified=bool(v.get("verified", False)),
            confidence=float(v.get("confidence", 0.0)),
            evidence=str(v.get("evidence", "")),
        )
        for v in verified_raw
    ]
    scores_raw: dict[str, Any] = old_state.get("quality_scores", {}) or {}
    review = ReviewContext(
        stage1_markers=stage1_markers,
        stage2_verified=stage2_verified,
        quality_scores={str(k): float(v) for k, v in scores_raw.items()},
        hallucination_flag=bool(old_state.get("hallucination_flag", False)),
    )

    return ReportState(
        base=base,
        collection=collection,
        writing=writing,
        review=review,
    )


def safe_status(raw: Any) -> Any:
    """Coerce a raw status value to a valid Literal."""
    valid = {"init", "collecting", "writing", "reviewing", "approved", "rejected", "published"}
    s = str(raw).strip().lower()
    if s in valid:
        return s
    return "init"
