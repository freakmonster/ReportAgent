"""Integration tests for flash_news workflow — graph construction & end-to-end execution.

Tests verify:
- WorkflowBuilder correctly builds flash_news graph from YAML template
- End-to-end execution with mocked nodes produces expected final state
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
    """Return 3 sample raw_docs while preserving existing collection fields."""
    existing_collection = state.get("collection", {})
    return {
        "collection": {
            "raw_docs": [
                {"title": "快讯1", "url": "https://example.com/1", "content": "内容摘要1"},
                {"title": "快讯2", "url": "https://example.com/2", "content": "内容摘要2"},
                {"title": "快讯3", "url": "https://example.com/3", "content": "内容摘要3"},
            ],
            "compressed_summary": existing_collection.get("compressed_summary", {}),
            "source_urls": [
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
            ],
            "chapter_plan": existing_collection.get("chapter_plan", []),
        },
        "base": {**state.get("base", {}), "status": "collecting"},
    }


async def _mock_writer(state: dict) -> dict:
    """Return 2 sample chapter drafts."""
    return {
        "writing": {
            "chapter_drafts": {
                "核心要点": "## 核心要点\n\n今日市场快讯核心要点。",
                "关键数据": "## 关键数据\n\n最新经济数据更新。",
            },
            "final_content": "",
            "citation_list": [],
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Graph construction
# ---------------------------------------------------------------------------


class TestFlashNewsGraphConstruction:
    """Verify flash_news graph is correctly built from YAML template."""

    def test_builds_compiled_graph(self) -> None:
        """WorkflowBuilder builds a CompiledStateGraph for flash_news."""
        from langgraph.graph.state import CompiledStateGraph

        from agents.workflows.builder import WorkflowBuilder

        graph = WorkflowBuilder().build("flash_news", ReportState)
        assert isinstance(graph, CompiledStateGraph)

    def test_has_six_nodes(self) -> None:
        """Flash news graph contains exactly 6 user-defined nodes."""
        from agents.workflows.builder import WorkflowBuilder

        graph = WorkflowBuilder().build("flash_news", ReportState)
        all_nodes = graph.get_graph().nodes
        # Filter out internal __start__ and __end__ nodes
        user_nodes = {
            k: v for k, v in all_nodes.items()
            if k not in ("__start__", "__end__")
        }
        assert len(user_nodes) == 6

        node_names = set(user_nodes.keys())
        expected = {
            "intent_classifier", "research_planner", "data_collector",
            "writer", "editor", "publisher",
        }
        assert node_names == expected


# ---------------------------------------------------------------------------
# Test 2: End-to-end execution
# ---------------------------------------------------------------------------


class TestFlashNewsEndToEnd:
    """Verify flash_news workflow runs end-to-end with mocked nodes."""

    @pytest.mark.asyncio
    async def test_end_to_end_execution(self) -> None:
        """End-to-end run produces published status, final content, and chapter plan."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.writer.entry", _mock_writer),
        ):
            graph = WorkflowBuilder().build("flash_news", ReportState)
            initial_state = create_initial_state(
                "wf-flash-1", "u-flash-1", "flash_news",
            )
            initial_state["base"]["user_input"] = "今日市场快讯分析"
            result = await graph.ainvoke(initial_state)

        # Verify final status
        assert result["base"]["status"] == "published"

        # Verify final content is a non-empty string
        assert isinstance(result["writing"]["final_content"], str)
        assert len(result["writing"]["final_content"]) > 0

        # Verify chapter_plan is a non-empty list (set by research_planner)
        assert isinstance(result["collection"]["chapter_plan"], list)
        assert len(result["collection"]["chapter_plan"]) > 0


# ---------------------------------------------------------------------------
# Test 3: SSE streaming
# ---------------------------------------------------------------------------


class TestFlashNewsSSEStream:
    """Verify flash_news SSE streaming produces expected events."""

    @pytest.mark.asyncio
    async def test_streams_six_events(self) -> None:
        """SSE stream yields exactly 6 node events (one per node)."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.writer.entry", _mock_writer),
        ):
            graph = WorkflowBuilder().build("flash_news", ReportState)
            initial_state = create_initial_state(
                "wf-flash-2", "u-flash-2", "flash_news",
            )
            initial_state["base"]["user_input"] = "今日市场快讯分析"

            events = []
            async for event in graph.astream(initial_state, stream_mode="updates"):
                events.append(event)

        assert len(events) == 6

    @pytest.mark.asyncio
    async def test_stream_contains_publisher_event(self) -> None:
        """At least one stream event contains a 'publisher' key."""
        from agents.workflows.builder import WorkflowBuilder

        with (
            patch("agents.nodes.data_collector.entry", _mock_data_collector),
            patch("agents.nodes.writer.entry", _mock_writer),
        ):
            graph = WorkflowBuilder().build("flash_news", ReportState)
            initial_state = create_initial_state(
                "wf-flash-3", "u-flash-3", "flash_news",
            )
            initial_state["base"]["user_input"] = "今日市场快讯分析"

            publisher_seen = False
            async for event in graph.astream(initial_state, stream_mode="updates"):
                if "publisher" in event:
                    publisher_seen = True

        assert publisher_seen, "No 'publisher' key found among stream events"
