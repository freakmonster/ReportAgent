"""Unit tests for StructuralHandler — output schema validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from harness.handlers.base import HandlerDecision  # noqa: E402
from harness.handlers.structural_handler import StructuralHandler  # noqa: E402
from harness.orchestrator.context import PostExecContext  # noqa: E402


class TestStructuralHandler:
    """Verify output structure, style, and safety checks."""

    @pytest.mark.asyncio
    async def test_clean_output_passes(self) -> None:
        handler = StructuralHandler()
        ctx = PostExecContext(node_name="writer", raw_output="# 标题\n\n正常内容。")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_script_tag_rejected(self) -> None:
        handler = StructuralHandler()
        ctx = PostExecContext(raw_output="Content <script>alert(1)</script>")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.REJECT

    @pytest.mark.asyncio
    async def test_empty_output_passes(self) -> None:
        handler = StructuralHandler()
        ctx = PostExecContext(raw_output="")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.PASS

    @pytest.mark.asyncio
    async def test_short_output_warns(self) -> None:
        handler = StructuralHandler()
        ctx = PostExecContext(node_name="writer", raw_output="hi")
        result = await handler.handle(object(), ctx)
        assert result.decision == HandlerDecision.FAIL

    @pytest.mark.asyncio
    async def test_wrong_context_type_passes(self) -> None:
        handler = StructuralHandler()
        result = await handler.handle(object(), object())
        assert result.decision == HandlerDecision.PASS
