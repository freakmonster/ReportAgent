"""Integration tests for deep_report workflow — full 10-node pipeline.

Tests verify:
- WorkflowBuilder correctly builds deep_report graph from YAML template
- Approved path: reviewer → publisher (skip human_review)
- Needs_human path: reviewer → human_review → publisher
- Rejected + retry path: reviewer → writer (retry loop < 3)
- Rejected + exhausted retries: reviewer → human_review
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
    """Return 3 sample raw_docs for deep research."""
    existing_collection = state.get("collection", {})
    return {
        "collection": {
            "raw_docs": [
                {
                    "title": "新能源汽车市场分析",
                    "url": "https://example.com/ev/1",
                    "content": "2026年上半年新能源汽车销量突破500万辆，同比增长35%。"
                              "比亚迪以180万辆销量继续领跑，市场份额达36%。",
                },
                {
                    "title": "电池技术路线对比",
                    "url": "https://example.com/ev/2",
                    "content": "固态电池技术路线逐渐清晰，宁德时代、比亚迪等企业加速布局。"
                              "磷酸铁锂电池仍占据60%以上市场份额。",
                },
                {
                    "title": "充电基础设施发展",
                    "url": "https://example.com/ev/3",
                    "content": "全国充电桩保有量突破1000万个，车桩比降至2.5:1。"
                              "超充技术普及推动充电效率大幅提升。",
                },
            ],
            "compressed_summary": existing_collection.get("compressed_summary", {}),
            "source_urls": [
                "https://example.com/ev/1",
                "https://example.com/ev/2",
                "https://example.com/ev/3",
            ],
            "chapter_plan": existing_collection.get("chapter_plan", []),
        },
        "base": {**state.get("base", {}), "status": "collecting"},
    }


async def _mock_data_processor(state: dict) -> dict:
    """Return processed chunks — deep_report specific node."""
    existing_collection = state.get("collection", {})
    return {
        "collection": {
            "raw_docs": existing_collection.get("raw_docs", []),
            "compressed_summary": existing_collection.get("compressed_summary", {}),
            "source_urls": existing_collection.get("source_urls", []),
            "chapter_plan": existing_collection.get("chapter_plan", []),
            "analysis": existing_collection.get("analysis", {}),
        },
        "base": {**state.get("base", {}), "status": "processing"},
    }


async def _mock_data_analyst(state: dict) -> dict:
    """Return analysis summary with key metrics."""
    existing_collection = state.get("collection", {})
    return {
        "collection": {
            "raw_docs": existing_collection.get("raw_docs", []),
            "compressed_summary": existing_collection.get("compressed_summary", {}),
            "source_urls": existing_collection.get("source_urls", []),
            "chapter_plan": existing_collection.get("chapter_plan", []),
            "analysis": {
                "doc_count": 3,
                "total_chars": 800,
                "key_metrics": ["新能源汽车销量", "市场份额", "充电桩数量"],
                "data_quality": "good",
            },
        },
        "base": {**state.get("base", {}), "status": "analyzing"},
    }


async def _mock_writer(state: dict) -> dict:
    """Return 3 chapter drafts with deep research content."""
    return {
        "writing": {
            "chapter_drafts": {
                "市场概览": "## 市场概览\n\n2026年上半年新能源汽车销量突破500万辆，"
                          "同比增长35%，市场保持高速增长态势。",
                "技术分析": "## 技术分析\n\n固态电池技术路线逐渐清晰，"
                          "磷酸铁锂仍占据60%以上市场份额。",
                "基础设施": "## 基础设施\n\n全国充电桩保有量突破1000万个，"
                          "车桩比降至2.5:1，超充技术加速普及。",
            },
            "final_content": "",
            "citation_list": [],
        },
    }


async def _mock_reviewer_approved(state: dict) -> dict:
    """Return decision='approved', high confidence."""
    return {
        "review": {
            "stage1_markers": [],
            "stage2_verified": [],
            "quality_scores": {"overall": 0.88, "completeness": 0.85, "accuracy": 0.92},
            "hallucination_flag": False,
            "decision": "approved",
            "confidence": 0.92,
        },
        "base": {**state.get("base", {}), "status": "reviewing"},
    }


async def _mock_reviewer_needs_human(state: dict) -> dict:
    """Return decision='needs_human', moderate confidence."""
    return {
        "review": {
            "stage1_markers": [],
            "stage2_verified": [],
            "quality_scores": {"overall": 0.60, "completeness": 0.55, "accuracy": 0.65},
            "hallucination_flag": False,
            "decision": "needs_human",
            "confidence": 0.62,
        },
        "base": {**state.get("base", {}), "status": "reviewing"},
    }


async def _mock_reviewer_rejected(state: dict) -> dict:
    """Return decision='rejected', low confidence (triggers retry)."""
    base = state.get("base", {})
    return {
        "review": {
            "stage1_markers": [],
            "stage2_verified": [],
            "quality_scores": {"overall": 0.35, "completeness": 0.30, "accuracy": 0.40},
            "hallucination_flag": True,
            "decision": "rejected",
            "confidence": 0.28,
        },
        "base": {**base, "status": "reviewing", "retry_count": base.get("retry_count", 0) + 1},
    }


async def _mock_human_review(state: dict) -> dict:
    """Mock human_review — preserve existing decision."""
    review: dict = state.get("review", {})
    return {
        "review": {**review, "decision": review.get("decision", "approved")},
        "base": {**state.get("base", {}), "status": "reviewing"},
    }


async def _mock_editor(state: dict) -> dict:
    """Mock editor — return writing state unchanged (avoid LLM calls)."""
    return {
        "writing": {**state.get("writing", {})},
    }


# ---------------------------------------------------------------------------
# Test 1: Graph construction
# ---------------------------------------------------------------------------


class TestDeepReportGraphConstruction:
    """Verify deep_report graph is correctly built from YAML template."""

    def test_builds_compiled_graph(self) -> None:
        """WorkflowBuilder builds a CompiledStateGraph for deep_report."""
        from langgraph.graph.state import CompiledStateGraph

        from agents.workflows.builder import WorkflowBuilder

        graph = WorkflowBuilder().build("deep_report", ReportState)
        assert isinstance(graph, CompiledStateGraph)

    def test_has_ten_nodes(self) -> None:
        """Deep report graph contains exactly 10 user-defined nodes."""
        from agents.workflows.builder import WorkflowBuilder

        graph = WorkflowBuilder().build("deep_report", ReportState)
        all_nodes = graph.get_graph().nodes
        user_nodes = {
            k: v for k, v in all_nodes.items()
            if k not in ("__start__", "__end__")
        }
        assert len(user_nodes) == 10

        node_names = set(user_nodes.keys())
        expected = {
            "intent_classifier", "research_planner", "data_collector",
            "data_processor", "data_analyst", "writer", "editor",
            "reviewer", "human_review", "publisher",
        }
        assert node_names == expected


# ---------------------------------------------------------------------------
# Test 2: End-to-end — approved path
# ---------------------------------------------------------------------------


class TestDeepReportApprovedPath:
    """Verify approved path: reviewer → publisher (skip human_review)."""

    @pytest.mark.asyncio
    async def test_approved_path_publishes_directly(self) -> None:
        """Approved review → publisher, human_review skipped."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_processor.entry", _mock_data_processor),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.editor.entry", _mock_editor),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_approved),
        ):
            graph = WorkflowBuilder().build("deep_report", ReportState)
            initial_state = create_initial_state("wf-dr-1", "u-dr-1", "deep_report")
            initial_state["base"]["user_input"] = "新能源汽车行业深度研究报告"
            result = await graph.ainvoke(initial_state)

        assert result["base"]["status"] == "published"
        assert isinstance(result["writing"]["final_content"], str)
        assert len(result["writing"]["final_content"]) > 0
        assert result["review"]["decision"] == "approved"


# ---------------------------------------------------------------------------
# Test 3: End-to-end — needs_human path
# ---------------------------------------------------------------------------


class TestDeepReportNeedsHumanPath:
    """Verify needs_human path: reviewer → human_review → publisher."""

    @pytest.mark.asyncio
    async def test_needs_human_path_routes_through_human_review(self) -> None:
        """Needs_human routes through human_review before publisher."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_processor.entry", _mock_data_processor),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.editor.entry", _mock_editor),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_needs_human),
            patch("agents.nodes.human_review.entry", _mock_human_review),
        ):
            graph = WorkflowBuilder().build("deep_report", ReportState)
            initial_state = create_initial_state("wf-dr-2", "u-dr-2", "deep_report")
            initial_state["base"]["user_input"] = "新能源汽车行业深度研究报告"
            result = await graph.ainvoke(initial_state)

        assert result["base"]["status"] == "published"
        assert result["review"]["decision"] == "needs_human"


# ---------------------------------------------------------------------------
# Test 4: End-to-end — rejected + retry path
# ---------------------------------------------------------------------------


class TestDeepReportRejectedRetryPath:
    """Verify rejected path with retry: reviewer → writer (retry < 3)."""

    @pytest.mark.asyncio
    async def test_rejected_with_retry_goes_back_to_writer(self) -> None:
        """Rejected + retry_count < 3 → loops back to writer."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_processor.entry", _mock_data_processor),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.editor.entry", _mock_editor),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_rejected),
            patch("agents.nodes.human_review.entry", _mock_human_review),
        ):
            graph = WorkflowBuilder().build("deep_report", ReportState)
            initial_state = create_initial_state("wf-dr-3", "u-dr-3", "deep_report")
            initial_state["base"]["user_input"] = "新能源汽车行业深度研究报告"
            initial_state["base"]["retry_count"] = 0
            result = await graph.ainvoke(initial_state)

        # retry_count should increment after retry through writer
        assert result["base"]["retry_count"] >= 1
        assert result["base"]["status"] in ("reviewing", "published")

    @pytest.mark.asyncio
    async def test_rejected_with_exhausted_retries_routes_to_human_review(self) -> None:
        """Rejected + retry_count >= 3 → goes to human_review."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_processor.entry", _mock_data_processor),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.editor.entry", _mock_editor),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_rejected),
            patch("agents.nodes.human_review.entry", _mock_human_review),
        ):
            graph = WorkflowBuilder().build("deep_report", ReportState)
            initial_state = create_initial_state("wf-dr-4", "u-dr-4", "deep_report")
            initial_state["base"]["user_input"] = "新能源汽车行业深度研究报告"
            initial_state["base"]["retry_count"] = 3  # already exhausted
            result = await graph.ainvoke(initial_state)

        assert result["base"]["status"] == "published"


# ---------------------------------------------------------------------------
# Test 5: SSE streaming
# ---------------------------------------------------------------------------


class TestDeepReportSSEStream:
    """Verify deep_report SSE streaming produces expected events."""

    @pytest.mark.asyncio
    async def test_streams_nine_events_approved_path(self) -> None:
        """SSE stream yields exactly 9 events on approved path (human_review skipped)."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_processor.entry", _mock_data_processor),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.editor.entry", _mock_editor),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_approved),
        ):
            graph = WorkflowBuilder().build("deep_report", ReportState)
            initial_state = create_initial_state("wf-dr-5", "u-dr-5", "deep_report")
            initial_state["base"]["user_input"] = "新能源汽车行业深度研究报告"

            events = []
            async for event in graph.astream(initial_state, stream_mode="updates"):
                events.append(event)

        assert len(events) == 9

    @pytest.mark.asyncio
    async def test_stream_contains_all_expected_nodes(self) -> None:
        """All 9 executed node keys appear among stream events."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.data_processor.entry", _mock_data_processor),
            patch("agents.nodes.data_analyst.entry", _mock_data_analyst),
            patch("agents.nodes.writer.entry", _mock_writer),
            patch("agents.nodes.editor.entry", _mock_editor),
            patch("agents.nodes.reviewer.entry", _mock_reviewer_approved),
        ):
            graph = WorkflowBuilder().build("deep_report", ReportState)
            initial_state = create_initial_state("wf-dr-6", "u-dr-6", "deep_report")
            initial_state["base"]["user_input"] = "新能源汽车行业深度研究报告"

            seen_keys: set[str] = set()
            async for event in graph.astream(initial_state, stream_mode="updates"):
                seen_keys.update(event.keys())

        expected = {
            "intent_classifier", "research_planner", "data_collector",
            "data_processor", "data_analyst", "writer", "editor",
            "reviewer", "publisher",
        }
        assert seen_keys == expected
