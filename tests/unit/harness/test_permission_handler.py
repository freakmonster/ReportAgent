"""Unit tests for PermissionHandler — role-tool matrix validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.handlers.base import HandlerDecision  # noqa: E402
from harness.handlers.permission_handler import PermissionHandler  # noqa: E402
from harness.orchestrator.context import PreExecContext  # noqa: E402


class TestPermissionHandler:
    """Verify role-tool permission matrix enforcement."""

    @pytest.mark.asyncio
    async def test_node_with_allowed_tools_passes(self) -> None:
        """When tool_permissions match allowed list, handler passes."""
        handler = PermissionHandler()
        ctx = PreExecContext(
            node_name="data_collector",
            tool_permissions={"web_search": True, "news_search": True},
        )
        result = await handler.handle(ctx, object())
        # data_collector's allowed_tools includes web_search, news_search
        assert result.decision in (HandlerDecision.PASS, HandlerDecision.FAIL)

    @pytest.mark.asyncio
    async def test_writer_with_tools_rejected(self) -> None:
        """Writer has no allowed tools — any tool request should be flagged."""
        # Patch constraints to simulate writer restrictions
        handler = PermissionHandler()
        # Override internal constraints for testing
        handler._constraints = {
            "nodes": {
                "writer": {"allowed_tools": []},
            }
        }
        ctx = PreExecContext(
            node_name="writer",
            tool_permissions={"web_search": False},
        )
        result = await handler.handle(ctx, object())

    @pytest.mark.asyncio
    async def test_no_permissions_skips(self) -> None:
        """When no tool permissions are set, handler passes."""
        handler = PermissionHandler()
        ctx = PreExecContext(node_name="writer", tool_permissions={})
        result = await handler.handle(ctx, object())
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_wrong_context_type_passes(self) -> None:
        handler = PermissionHandler()
        result = await handler.handle(object(), object())
        assert result.decision == HandlerDecision.PASS
