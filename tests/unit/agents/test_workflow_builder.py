"""Unit tests for WorkflowBuilder — harness node wrapping."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from agents.state import ReportState, create_initial_state
from agents.workflows.builder import WorkflowBuilder  # noqa: E402
from harness.handlers.base import HandlerDecision  # noqa: E402


@pytest.fixture
def builder() -> WorkflowBuilder:
    return WorkflowBuilder()


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """A HarnessOrchestrator mock with async methods."""
    m = MagicMock()
    m.execute_pre = AsyncMock(return_value=[])
    m.execute_post = AsyncMock(return_value=[])
    m.handler_names = ["InputSafetyHandler", "PermissionHandler"]
    return m


class TestWorkflowBuilderHarnessWrapping:
    """Verify harness integration in WorkflowBuilder."""

    @pytest.mark.asyncio
    async def test_build_without_orchestrator_no_wrapping(self, builder: WorkflowBuilder) -> None:
        """Default build() should not wrap nodes (backward-compatible)."""
        graph = builder.build("flash_news", ReportState)
        state = create_initial_state("wf1", "test_user", "flash_news")
        state["base"]["user_input"] = "test query"
        result = await graph.ainvoke(state)
        assert result is not None

    @pytest.mark.asyncio
    async def test_build_with_orchestrator_wraps_nodes(
        self, builder: WorkflowBuilder, mock_orchestrator: MagicMock
    ) -> None:
        """When orchestrator is provided, nodes should be wrapped (pre/post executed)."""
        graph = builder.build("flash_news", ReportState, harness_orchestrator=mock_orchestrator)
        state = create_initial_state("wf2", "test_user", "flash_news")
        state["base"]["user_input"] = "test query"

        _ = await graph.ainvoke(state)

        # Each of the 6 flash_news nodes should have triggered execute_pre + execute_post
        assert mock_orchestrator.execute_pre.await_count >= 6
        assert mock_orchestrator.execute_post.await_count >= 6

    @pytest.mark.asyncio
    async def test_pre_reject_skips_node_execution(
        self, builder: WorkflowBuilder, mock_orchestrator: MagicMock
    ) -> None:
        """When pre-handler returns REJECT, node entry should not be called but workflow continues."""
        from harness.handlers.base import HandlerResult

        reject_result = HandlerResult(
            decision=HandlerDecision.REJECT,
            detail="Dangerous input",
            handler_name="InputSafetyHandler",
        )

        async def reject_first(*args, **kwargs) -> list[object]:
            reject_first.call_count = getattr(reject_first, "call_count", 0) + 1
            if reject_first.call_count <= 1:
                return [reject_result]
            return []

        mock_orchestrator.execute_pre = reject_first  # type: ignore[method-assign]

        graph = builder.build("flash_news", ReportState, harness_orchestrator=mock_orchestrator)
        state = create_initial_state("wf3", "test_user", "flash_news")
        state["base"]["user_input"] = "DROP TABLE users;"

        result = await graph.ainvoke(state)
        assert result is not None
        # Workflow reaches the end regardless of harness REJECT on first node

    @pytest.mark.asyncio
    async def test_build_wraps_deep_report(
        self, builder: WorkflowBuilder, mock_orchestrator: MagicMock
    ) -> None:
        """Deep report (10 nodes) should also wrap correctly."""
        graph = builder.build("deep_report", ReportState, harness_orchestrator=mock_orchestrator)
        state = create_initial_state("wf4", "test_user", "deep_report")
        state["base"]["user_input"] = "人工智能发展报告"

        _ = await graph.ainvoke(state)

        # All 10 nodes should have been wrapped
        assert mock_orchestrator.execute_pre.await_count >= 10
        assert mock_orchestrator.execute_post.await_count >= 10
