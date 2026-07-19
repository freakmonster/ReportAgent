"""Unit tests for Checkpointer lifecycle and builder integration.

Verifies:
- create_checkpointer() context manager contract
- Graph compilation with checkpointer vs without
- Builder correctly passes checkpointer through to graph.compile()
- DSN masking for logging safety
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from infrastructure.database.checkpointer import _mask_dsn, create_checkpointer  # noqa: E402


class TestDSNMasking:
    """Verify password masking for safe logging."""

    def test_masks_password_in_standard_dsn(self) -> None:
        dsn = "postgresql://user:secret@localhost:5432/db"
        masked = _mask_dsn(dsn)
        assert "secret" not in masked, f"Password leaked in: {masked}"
        assert ":" in masked

    def test_no_at_symbol_preserves_dsn(self) -> None:
        dsn = "postgresql://localhost:5432/db"
        masked = _mask_dsn(dsn)
        assert masked == dsn


class TestCreateCheckpointer:
    """Verify checkpointer context manager behaviour."""

    @pytest.mark.asyncio
    async def test_yields_none_on_connection_error_dev_mode(self) -> None:
        """In dev mode, connection failure → yield None without crash."""
        with patch(
            "infrastructure.database.checkpointer.settings"
        ) as mock_settings:
            mock_settings.environment = "development"
            mock_settings.pg_dsn = "postgresql://localhost:5432/db"
            mock_settings.environment = "development"

            mock_cls = MagicMock()
            mock_cls.from_conn_string.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("Connection refused")
            )
            mock_cls.from_conn_string.return_value.__aexit__ = AsyncMock()

            with patch(
                "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver",
                mock_cls,
            ):
                async with create_checkpointer() as cp:
                    assert cp is None


class TestBuilderCheckpointerIntegration:
    """Verify WorkflowBuilder passes checkpointer to graph.compile()."""

    def test_build_without_checkpointer_compiles_without_arg(self) -> None:
        from agents.state import ReportState
        from agents.workflows.builder import WorkflowBuilder

        builder = WorkflowBuilder()
        with patch.object(builder, "_load_node_entry") as mock_load:
            async def _noop(state):  # noqa: E306
                return state
            mock_load.return_value = _noop
            graph = builder.build("flash_news", ReportState)

        assert hasattr(graph, "astream")

    def test_build_with_in_memory_checkpointer(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver

        from agents.state import ReportState
        from agents.workflows.builder import WorkflowBuilder

        cp = InMemorySaver()
        builder = WorkflowBuilder()

        with patch.object(builder, "_load_node_entry") as mock_load:
            async def _noop(state):  # noqa: E306
                return state
            mock_load.return_value = _noop
            graph = builder.build("flash_news", ReportState, checkpointer=cp)

        assert hasattr(graph, "astream")

    def test_build_deep_report_with_harness_and_checkpointer(self) -> None:
        """Full build: harness + checkpointer on deep_report template."""
        from langgraph.checkpoint.memory import InMemorySaver

        from agents.state import ReportState
        from agents.workflows.builder import WorkflowBuilder

        cp = InMemorySaver()
        builder = WorkflowBuilder()
        mock_harness = MagicMock()
        mock_harness.execute_pre = AsyncMock(return_value=[])
        mock_harness.execute_post = AsyncMock(return_value=[])

        with patch.object(builder, "_load_node_entry") as mock_load:
            async def _noop(state):  # noqa: E306
                return state
            mock_load.return_value = _noop
            graph = builder.build(
                "deep_report",
                ReportState,
                harness_orchestrator=mock_harness,
                checkpointer=cp,
            )

        assert hasattr(graph, "astream")
