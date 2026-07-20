"""Integration tests for earnings_analysis workflow — graph construction & end-to-end execution.

Tests verify:
- WorkflowBuilder correctly builds earnings_analysis graph from YAML template
- End-to-end execution with mocked nodes produces expected final state
- Conditional routing (approved → publisher, needs_human → human_review → publisher)
- SSE streaming produces expected event sequence
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402

from agents.state import ReportState, create_initial_state  # noqa: E402

# ---------------------------------------------------------------------------
# Mock helpers — return fixed data without real network/LLM calls
# ---------------------------------------------------------------------------


async def _mock_data_collector(state: dict) -> dict:
    """Return 3 finance/earnings themed raw_docs."""
    existing_collection = state.get("collection", {})
    return {
        "collection": {
            "raw_docs": [
                {
                    "title": "苹果Q2财报超预期",
                    "url": "https://example.com/finance/1",
                    "content": "苹果公司发布2026财年第二季度财报，营收同比增长8%至1200亿美元。"
                    "净利润320亿美元，同比增长12%。服务业务收入持续增长。",
                },
                {
                    "title": "特斯拉毛利率下滑分析",
                    "url": "https://example.com/finance/2",
                    "content": "特斯拉最新财报显示毛利率降至18.5%，低于市场预期的19.2%。"
                    "主要受降价策略影响，但交付量同比增长25%。",
                },
                {
                    "title": "腾讯财报：广告收入增长强劲",
                    "url": "https://example.com/finance/3",
                    "content": "腾讯控股发布季度财报，总营收1800亿元，同比增长11%。"
                    "广告业务收入同比增长20%，成为第二大收入来源。",
                },
            ],
            "compressed_summary": existing_collection.get("compressed_summary", {}),
            "source_urls": [
                "https://example.com/finance/1",
                "https://example.com/finance/2",
                "https://example.com/finance/3",
            ],
            "chapter_plan": existing_collection.get("chapter_plan", []),
        },
        "base": {**state.get("base", {}), "status": "collecting"},
    }


async def _mock_data_analyst(state: dict) -> dict:
    """Return a simple analysis summary dict."""
    existing_collection = state.get("collection", {})
    return {
        "collection": {
            "raw_docs": existing_collection.get("raw_docs", []),
            "compressed_summary": existing_collection.get("compressed_summary", {}),
            "source_urls": existing_collection.get("source_urls", []),
            "chapter_plan": existing_collection.get("chapter_plan", []),
            "analysis": {
                "doc_count": 3,
                "total_chars": 500,
                "key_metrics": ["营收增长", "净利润", "毛利率"],
                "data_quality": "good",
            },
        },
        "base": {**state.get("base", {}), "status": "analyzing"},
    }


async def _mock_writer(state: dict) -> dict:
    """Return 2 chapter drafts with earnings analysis content."""
    return {
        "writing": {
            "chapter_drafts": {
                "收入分析": "## 收入分析\n\n苹果营收同比增长8%至1200亿美元，"
                "腾讯总营收1800亿元同比增长11%。两家公司收入增长稳健。",
                "利润分析": "## 利润分析\n\n苹果净利润320亿美元，同比增长12%。"
                "特斯拉毛利率降至18.5%，低于市场预期。",
            },
            "final_content": "",
            "citation_list": [],
        },
    }


async def _mock_reviewer_approved(state: dict) -> dict:
    """Return decision='approved', confidence=0.95."""
    return {
        "review": {
            "stage1_markers": [],
            "stage2_verified": [],
            "quality_scores": {"overall": 0.85, "completeness": 0.8, "accuracy": 0.9},
            "hallucination_flag": False,
            "decision": "approved",
            "confidence": 0.95,
        },
        "base": {**state.get("base", {}), "status": "reviewing"},
    }


async def _mock_reviewer_needs_human(state: dict) -> dict:
    """Return decision='needs_human', confidence=0.60."""
    return {
        "review": {
            "stage1_markers": [],
            "stage2_verified": [],
            "quality_scores": {"overall": 0.55, "completeness": 0.5, "accuracy": 0.6},
            "hallucination_flag": False,
            "decision": "needs_human",
            "confidence": 0.60,
        },
        "base": {**state.get("base", {}), "status": "reviewing"},
    }


async def _mock_human_review(state: dict) -> dict:
    """Mock human_review — preserve existing decision instead of resetting to approved."""
    review: dict = state.get("review", {})
    return {
        "review": {**review, "decision": review.get("decision", "approved")},
        "base": {**state.get("base", {}), "status": "reviewing"},
    }


# ---------------------------------------------------------------------------
# Test 1: Graph construction
# ---------------------------------------------------------------------------


class TestEarningsAnalysisGraphConstruction:
    """Verify earnings_analysis graph is correctly built from YAML template."""

    def test_builds_compiled_graph(self) -> None:
        """WorkflowBuilder builds a CompiledStateGraph for earnings_analysis."""
        from langgraph.graph.state import CompiledStateGraph

        from agents.workflows.builder import WorkflowBuilder

        graph = WorkflowBuilder().build("earnings_analysis", ReportState)
        assert isinstance(graph, CompiledStateGraph)

    def test_has_nine_nodes(self) -> None:
        """Earnings analysis graph contains exactly 9 user-defined nodes."""
        from agents.workflows.builder import WorkflowBuilder

        graph = WorkflowBuilder().build("earnings_analysis", ReportState)
        all_nodes = graph.get_graph().nodes
        # Filter out internal __start__ and __end__ nodes
        user_nodes = {k: v for k, v in all_nodes.items() if k not in ("__start__", "__end__")}
        assert len(user_nodes) == 9

        node_names = set(user_nodes.keys())
        expected = {
            "intent_classifier",
            "research_planner",
            "data_collector",
            "data_analyst",
            "writer",
            "editor",
            "reviewer",
            "human_review",
            "publisher",
        }
        assert node_names == expected


# ---------------------------------------------------------------------------
# Test 2: End-to-end — approved path
# ---------------------------------------------------------------------------


class TestEarningsAnalysisApprovedPath:
    """Verify earnings_analysis approved path (reviewer → publisher, skip human_review)."""

    @pytest.mark.asyncio
    async def test_approved_path_publishes_directly(self) -> None:
        """Approved review routes directly to publisher, bypassing human_review."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_approved),
        ):
            graph = WorkflowBuilder().build("earnings_analysis", ReportState)
            initial_state = create_initial_state(
                "wf-ea-1",
                "u-ea-1",
                "earnings_analysis",
            )
            initial_state["base"]["user_input"] = "分析最新财报数据"
            result = await graph.ainvoke(initial_state)

        # Verify final status
        assert result["base"]["status"] == "published"

        # Verify final content is a non-empty string
        assert isinstance(result["writing"]["final_content"], str)
        assert len(result["writing"]["final_content"]) > 0

        # Verify review decision is 'approved'
        assert result["review"]["decision"] == "approved"


# ---------------------------------------------------------------------------
# Test 3: End-to-end — needs_human path
# ---------------------------------------------------------------------------


class TestEarningsAnalysisNeedsHumanPath:
    """Verify earnings_analysis needs_human path (reviewer → human_review → publisher)."""

    @pytest.mark.asyncio
    async def test_needs_human_path_routes_through_human_review(self) -> None:
        """Needs_human review routes through human_review node before publisher."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_needs_human),
            patch("agents.nodes.human_review.entry", _mock_human_review),
        ):
            graph = WorkflowBuilder().build("earnings_analysis", ReportState)
            initial_state = create_initial_state(
                "wf-ea-2",
                "u-ea-2",
                "earnings_analysis",
            )
            initial_state["base"]["user_input"] = "分析最新财报数据"
            result = await graph.ainvoke(initial_state)

        # Verify final status
        assert result["base"]["status"] == "published"

        # Verify review decision is 'needs_human' (human_review mock preserves it)
        assert result["review"]["decision"] == "needs_human"


# ---------------------------------------------------------------------------
# Test 4: SSE streaming
# ---------------------------------------------------------------------------


class TestEarningsAnalysisSSEStream:
    """Verify earnings_analysis SSE streaming produces expected events."""

    @pytest.mark.asyncio
    async def test_streams_eight_events(self) -> None:
        """SSE stream yields exactly 8 node events (human_review is skipped in approved path)."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_approved),
        ):
            graph = WorkflowBuilder().build("earnings_analysis", ReportState)
            initial_state = create_initial_state(
                "wf-ea-3",
                "u-ea-3",
                "earnings_analysis",
            )
            initial_state["base"]["user_input"] = "分析最新财报数据"

            events = []
            async for event in graph.astream(initial_state, stream_mode="updates"):
                events.append(event)

        assert len(events) == 8

    @pytest.mark.asyncio
    async def test_stream_contains_all_expected_nodes(self) -> None:
        """All 8 executed node keys appear among stream events (human_review is skipped)."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_approved),
        ):
            graph = WorkflowBuilder().build("earnings_analysis", ReportState)
            initial_state = create_initial_state(
                "wf-ea-4",
                "u-ea-4",
                "earnings_analysis",
            )
            initial_state["base"]["user_input"] = "分析最新财报数据"

            seen_keys: set[str] = set()
            async for event in graph.astream(initial_state, stream_mode="updates"):
                seen_keys.update(event.keys())

        expected = {
            "intent_classifier",
            "research_planner",
            "data_collector",
            "data_analyst",
            "writer",
            "editor",
            "reviewer",
            "publisher",
        }
        assert seen_keys == expected
