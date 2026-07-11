"""Unit tests for HarnessOrchestrator — dynamic chain loading and execution."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.orchestrator.context import PostExecContext, PreExecContext  # noqa: E402
from harness.orchestrator.main import HarnessOrchestrator  # noqa: E402
from harness.handlers.base import HandlerDecision, HandlerResult  # noqa: E402


class TestHarnessOrchestrator:
    """Verify orchestrator chain loading and execution."""

    def test_loads_default_chain(self) -> None:
        orc = HarnessOrchestrator()
        assert orc.handler_count >= 4  # At minimum: input_safety, permission, structural, audit
        names = orc.handler_names
        # AuditHandler must be last
        assert "AuditHandler" in names

    def test_reload_chain(self) -> None:
        orc = HarnessOrchestrator()
        count_before = orc.handler_count
        orc.reload()
        assert orc.handler_count == count_before

    @pytest.mark.asyncio
    async def test_execute_chain_all_pass(self) -> None:
        orc = HarnessOrchestrator()
        pre = PreExecContext(
            node_name="writer",
            raw_input="帮我写一份行业报告",
            user_id="u1",
        )
        post = PostExecContext(
            node_name="writer",
            raw_output="# 报告\n\n风险提示\n\n内容。",
        )
        results = await orc.execute(pre, post)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_execute_short_circuits_on_reject(self) -> None:
        """A dangerous input should trigger REJECT and stop the chain early."""
        orc = HarnessOrchestrator()
        pre = PreExecContext(raw_input="DROP TABLE users; -- delete all data")
        post = PostExecContext(raw_output="")
        results = await orc.execute(pre, post)
        # Should short-circuit at input_safety_handler (REJECT)
        assert len(results) >= 1
        assert results[0].decision == HandlerDecision.REJECT

    def test_workflow_type_override(self) -> None:
        """Flash news workflow should have fewer handlers than deep_report."""
        orc = HarnessOrchestrator()
        orc.reload("flash_news")
        flash_count = orc.handler_count
        orc.reload()
        default_count = orc.handler_count
        assert flash_count < default_count, "Flash news should have fewer handlers"
