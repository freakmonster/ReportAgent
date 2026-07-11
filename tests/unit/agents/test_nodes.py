"""Unit tests for LangGraph nodes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from agents.state import create_initial_state  # noqa: E402


class TestIntentClassifier:
    """Verify intent classifier node."""

    @pytest.mark.asyncio
    async def test_classifies_report(self) -> None:
        from agents.nodes.intent_classifier import entry
        state = create_initial_state("wf-1", "u1")
        state["base"]["user_input"] = "帮我写一份新能源汽车行业深度分析研报"
        result = await entry(state)
        assert result["base"]["intent"] == "report"
        assert result["base"]["template_name"] in ("", "deep_report", "flash_news", "earnings_analysis")

    @pytest.mark.asyncio
    async def test_classifies_chat(self) -> None:
        from agents.nodes.intent_classifier import entry
        state = create_initial_state("wf-2", "u2")
        state["base"]["user_input"] = "你好"
        result = await entry(state)
        assert result["base"]["intent"] == "chat"


class TestResearchPlanner:
    """Verify research planner node."""

    @pytest.mark.asyncio
    async def test_plans_deep_report(self) -> None:
        from agents.nodes.research_planner import entry
        state = create_initial_state("wf-3", "u3", "deep_report")
        result = await entry(state)
        chapters = result["collection"]["chapter_plan"]
        assert len(chapters) >= 5
        assert "风险提示" in chapters

    @pytest.mark.asyncio
    async def test_plans_flash_news(self) -> None:
        from agents.nodes.research_planner import entry
        state = create_initial_state("wf-4", "u4", "flash_news")
        result = await entry(state)
        chapters = result["collection"]["chapter_plan"]
        assert len(chapters) >= 2


class TestDataCollector:
    """Verify data collector node."""

    @pytest.mark.asyncio
    async def test_collects_data(self) -> None:
        from agents.nodes.data_collector import entry
        state = create_initial_state("wf-5", "u5")
        result = await entry(state)
        assert len(result["collection"]["raw_docs"]) >= 1
        assert result["collection"]["source_urls"]


class TestDataProcessor:
    """Verify data processor Map-Reduce."""

    @pytest.mark.asyncio
    async def test_compresses_data(self) -> None:
        from agents.nodes.data_processor import entry
        state = create_initial_state("wf-6", "u6")
        state["collection"]["raw_docs"] = [
            {"title": "T", "url": "U", "content": "新能源市场增长迅速，2026年销量突破500万辆。"}
        ]
        result = await entry(state)
        compressed = result["collection"]["compressed_summary"]
        assert len(compressed) >= 1

    @pytest.mark.asyncio
    async def test_empty_docs_ok(self) -> None:
        from agents.nodes.data_processor import entry
        state = create_initial_state("wf-99", "u99")
        result = await entry(state)
        assert isinstance(result, dict)


class TestWriter:
    """Verify writer node chapter generation."""

    @pytest.mark.asyncio
    async def test_writes_chapters(self) -> None:
        from agents.nodes.writer import entry
        state = create_initial_state("wf-7", "u7")
        state["collection"]["compressed_summary"] = {
            "市场概况": "新能源汽车市场快速增长。",
            "风险提示": "投资有风险。",
        }
        result = await entry(state)
        drafts = result["writing"]["chapter_drafts"]
        assert "市场概况" in drafts
        assert "风险提示" in drafts


class TestEditor:
    """Verify editor node."""

    @pytest.mark.asyncio
    async def test_edits_chapters(self) -> None:
        from agents.nodes.editor import entry
        state = create_initial_state("wf-8", "u8")
        state["writing"]["chapter_drafts"] = {"ch1": "raw content", "ch2": "another one"}
        result = await entry(state)
        edited = result["writing"]["chapter_drafts"]
        assert "ch1" in edited
        assert edited["ch1"].endswith("。") or edited["ch1"].endswith(".")


class TestPublisher:
    """Verify publisher node."""

    @pytest.mark.asyncio
    async def test_publishes_report(self) -> None:
        from agents.nodes.publisher import entry
        state = create_initial_state("wf-9", "u9")
        state["writing"]["chapter_drafts"] = {"摘要": "内容", "风险提示": "风险"}
        state["writing"]["citation_list"] = ["来源1"]
        result = await entry(state)
        final = result["writing"]["final_content"]
        assert "# 智能研报" in final
        assert "摘要" in final
        assert "风险提示" in final

    @pytest.mark.asyncio
    async def test_sets_published_status(self) -> None:
        from agents.nodes.publisher import entry
        state = create_initial_state("wf-10", "u10")
        state["writing"]["chapter_drafts"] = {"ch": "c"}
        result = await entry(state)
        assert result["base"]["status"] == "published"


class TestReviewer:
    """Verify reviewer node."""

    @pytest.mark.asyncio
    async def test_reviews_content(self) -> None:
        from agents.nodes.reviewer import entry
        state = create_initial_state("wf-11", "u11")
        state["writing"]["final_content"] = "# 报告\n\n内容包括 风险提示\n\n数据来源。"
        result = await entry(state)
        assert "decision" in result["review"]


class TestHumanReview:
    """Verify human review node."""

    @pytest.mark.asyncio
    async def test_approves(self) -> None:
        from agents.nodes.human_review import entry
        state = create_initial_state("wf-12", "u12")
        result = await entry(state)
        assert result["review"]["decision"] == "approved"
