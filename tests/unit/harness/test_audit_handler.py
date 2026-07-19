"""Unit tests for AuditHandler — trace logging."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.handlers.audit_handler import AuditHandler  # noqa: E402
from harness.handlers.base import HandlerDecision  # noqa: E402
from harness.orchestrator.context import PostExecContext, PreExecContext  # noqa: E402


class TestAuditHandler:
    """Verify audit logging behavior."""

    @pytest.mark.asyncio
    async def test_always_returns_pass(self) -> None:
        """Audit handler never blocks execution."""
        handler = AuditHandler()
        pre = PreExecContext(node_name="writer", user_id="u1", raw_input="test")
        post = PostExecContext(node_name="writer", raw_output="output", duration_ms=123)
        result = await handler.handle(pre, post)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_logs_accumulate(self) -> None:
        handler = AuditHandler()
        handler.clear()
        pre = PreExecContext(node_name="w1", raw_input="in1")
        post = PostExecContext(raw_output="out1", duration_ms=50)

        await handler.handle(pre, post)
        await handler.handle(pre, post)

        log = handler.get_audit_log()
        assert len(log) == 2
        assert log[0]["node_name"] == "w1"

    @pytest.mark.asyncio
    async def test_log_export_as_json(self) -> None:
        handler = AuditHandler()
        handler.clear()
        await handler.handle(
            PreExecContext(node_name="n", raw_input="x"),
            PostExecContext(raw_output="y"),
        )
        json_str = handler.get_log_as_json()
        assert "n" in json_str
        assert "output_length" in json_str

    @pytest.mark.asyncio
    async def test_clear_resets_log(self) -> None:
        handler = AuditHandler()
        await handler.handle(
            PreExecContext(raw_input="x"), PostExecContext(raw_output="y")
        )
        handler.clear()
        assert handler.get_audit_log() == []
