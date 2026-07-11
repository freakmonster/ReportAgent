"""Unit tests for nested State Schemas and migrator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from agents.state import ReportState, create_initial_state  # noqa: E402
from agents.state.schemas.base import BaseContext  # noqa: E402
from agents.state.schemas.collection import CollectionContext, Document  # noqa: E402
from agents.state.schemas.writing import WritingContext  # noqa: E402
from agents.state.schemas.review import ReviewContext, ClaimMarker, VerifiedClaim  # noqa: E402
from agents.state.migrator import upgrade_v1_to_v2  # noqa: E402


class TestNestedState:
    """Verify nested state creation and structure."""

    def test_create_initial_state(self) -> None:
        state = create_initial_state("wf-1", "user-1")
        assert state["base"]["workflow_id"] == "wf-1"
        assert state["base"]["status"] == "init"
        assert state["base"]["template_name"] == "deep_report"
        assert state["collection"]["raw_docs"] == []
        assert state["collection"]["compressed_summary"] == {}
        assert state["writing"]["chapter_drafts"] == {}
        assert state["review"]["hallucination_flag"] is False

    def test_base_context_has_required_fields(self) -> None:
        bc: BaseContext = {
            "workflow_id": "w1", "user_id": "u1", "retry_count": 0,
            "version": 1, "status": "init", "template_name": "deep_report",
        }
        assert bc["version"] == 1
        assert bc["template_name"] == "deep_report"

    def test_collection_context_document_type(self) -> None:
        doc: Document = {"title": "Test", "url": "https://x.com", "content": "body"}
        cc: CollectionContext = {
            "raw_docs": [doc], "compressed_summary": {}, "source_urls": []
        }
        assert len(cc["raw_docs"]) == 1

    def test_writing_context(self) -> None:
        wc: WritingContext = {
            "chapter_drafts": {"ch1": "content"},
            "final_content": "",
            "citation_list": ["cite1"],
        }
        assert "ch1" in wc["chapter_drafts"]

    def test_review_context(self) -> None:
        rc: ReviewContext = {
            "stage1_markers": [],
            "stage2_verified": [],
            "quality_scores": {},
            "hallucination_flag": False,
        }
        assert rc["hallucination_flag"] is False

    def test_state_isolated_by_context(self) -> None:
        """Modifying one sub-context doesn't affect others."""
        state = create_initial_state("wf-2", "u2")
        state["collection"]["raw_docs"].append({"title": "T", "url": "U", "content": "C"})
        assert state["writing"]["chapter_drafts"] == {}
        assert state["review"]["stage1_markers"] == []


class TestMigrator:
    """Verify V1→V2 migration."""

    def test_upgrade_flat_to_nested(self) -> None:
        old = {
            "workflow_id": "wf-old",
            "user_id": "u-old",
            "retry_count": 2,
            "status": "writing",
            "template_name": "flash_news",
            "raw_docs": [{"title": "T", "url": "U", "content": "C"}],
            "compressed_summary": {"ch1": "summary"},
            "source_urls": ["U"],
            "chapter_drafts": {"ch1": "draft"},
            "final_content": "final",
            "citation_list": ["cite1"],
            "quality_scores": {"overall": 0.8},
            "hallucination_flag": True,
        }
        state = upgrade_v1_to_v2(old)
        assert state["base"]["workflow_id"] == "wf-old"
        assert state["base"]["retry_count"] == 2
        assert state["base"]["template_name"] == "flash_news"
        assert len(state["collection"]["raw_docs"]) == 1
        assert state["collection"]["compressed_summary"]["ch1"] == "summary"
        assert state["writing"]["chapter_drafts"]["ch1"] == "draft"
        assert state["writing"]["citation_list"] == ["cite1"]

    def test_upgrade_empty_state(self) -> None:
        state = upgrade_v1_to_v2({})
        assert state["base"]["workflow_id"] == ""
        assert state["base"]["retry_count"] == 0

    def test_upgrade_preserves_review_data(self) -> None:
        old = {"stage1_markers": [{"text": "abc", "entity_type": "pct", "position": 5, "has_citation": True, "source": "[1]"}]}
        state = upgrade_v1_to_v2(old)
        assert len(state["review"]["stage1_markers"]) == 1
        assert state["review"]["stage1_markers"][0]["text"] == "abc"
