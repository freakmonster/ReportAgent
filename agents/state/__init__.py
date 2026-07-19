"""State — nested ReportState combining all sub-contexts."""

from __future__ import annotations

from typing import TypedDict

from agents.state.schemas.base import BaseContext
from agents.state.schemas.collection import CollectionContext
from agents.state.schemas.review import ReviewContext
from agents.state.schemas.writing import WritingContext


class ReportState(TypedDict):
    """Aggregated LangGraph state — nested context architecture.

    V2.2 design: each phase gets its own TypedDict to avoid monolithic
    State anti-pattern (AGENTS.md §1.3).
    """
    base: BaseContext
    collection: CollectionContext
    writing: WritingContext
    review: ReviewContext


def create_initial_state(
    workflow_id: str,
    user_id: str,
    template_name: str = "deep_report",
    tenant_id: str = "default",
    model: str = "deepseek-flash",
    session_id: str = "",
) -> ReportState:
    """Create a fresh ReportState with all default values.

    Args:
        workflow_id: Unique workflow identifier.
        user_id: User initiating the workflow.
        template_name: Template to use.
        tenant_id: Multi-tenant isolation identifier.
        model: LLM model to use (deepseek-flash/pro, qwen-8b/32b/max).
        session_id: Session identifier for short-term memory association.

    Returns:
        Populated ReportState ready for LangGraph execution.
    """
    return ReportState(
        base=BaseContext(
            workflow_id=workflow_id,
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
            retry_count=0,
            version=1,
            status="init",
            template_name=template_name,
            model=model,
        ),
        collection=CollectionContext(
            raw_docs=[],
            compressed_summary={},
            source_urls=[],
            analysis={},
        ),
        writing=WritingContext(
            chapter_drafts={},
            final_content="",
            citation_list=[],
        ),
        review=ReviewContext(
            stage1_markers=[],
            stage2_verified=[],
            quality_scores={},
            hallucination_flag=False,
        ),
    )
