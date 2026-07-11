"""Unit tests for internal file manager tool."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from mcp_tools.internal_tools.file_manager import (  # noqa: E402
    FileManagerError,
    delete_report,
    list_versions,
    read_report,
    read_report_tool,
    save_report,
    save_report_tool,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_report_dir() -> Path:
    """Create a temporary directory for report I/O tests."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# ---------------------------------------------------------------------------
# save_report tests
# ---------------------------------------------------------------------------


class TestSaveReport:
    """Verify report saving behavior."""

    @pytest.mark.asyncio
    async def test_save_report_creates_file(self, temp_report_dir: Path) -> None:
        """save_report writes a .md file with frontmatter."""
        result = await save_report(
            workflow_id="wf-001",
            content="# Test Report\n\nContent here.",
            metadata={"title": "Test", "author": "AI"},
            report_dir=temp_report_dir,
        )

        assert result["success"] is True
        assert result["workflow_id"] == "wf-001"
        assert "timestamp" in result

        # Verify file exists and has correct content
        saved_files = list(temp_report_dir.glob("wf-001_*.md"))
        assert len(saved_files) == 1
        content = saved_files[0].read_text(encoding="utf-8")
        assert "workflow_id: wf-001" in content
        assert "title: Test" in content
        assert "# Test Report" in content

    @pytest.mark.asyncio
    async def test_save_report_creates_directory(self, temp_report_dir: Path) -> None:
        """save_report creates the report directory if it doesn't exist."""
        nested_dir = temp_report_dir / "sub" / "reports"
        result = await save_report(
            workflow_id="wf-002",
            content="Content",
            report_dir=nested_dir,
        )
        assert result["success"] is True
        assert nested_dir.exists()
        files = list(nested_dir.glob("*.md"))
        assert len(files) == 1

    @pytest.mark.asyncio
    async def test_save_report_without_metadata(self, temp_report_dir: Path) -> None:
        """save_report works without metadata."""
        result = await save_report(
            workflow_id="wf-003",
            content="Minimal content.",
            report_dir=temp_report_dir,
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_save_report_multiple_versions(self, temp_report_dir: Path) -> None:
        """Multiple saves for same workflow_id create multiple versions."""
        await save_report("wf-004", "Version 1", report_dir=temp_report_dir)
        import asyncio
        await asyncio.sleep(0.02)
        await save_report("wf-004", "Version 2", report_dir=temp_report_dir)

        files = sorted(temp_report_dir.glob("wf-004_*.md"))
        assert len(files) >= 2


# ---------------------------------------------------------------------------
# read_report tests
# ---------------------------------------------------------------------------


class TestReadReport:
    """Verify report reading behavior."""

    @pytest.mark.asyncio
    async def test_read_report_returns_latest(self, temp_report_dir: Path) -> None:
        """read_report returns the latest version by default."""
        await save_report("wf-010", "First version.", report_dir=temp_report_dir)
        await save_report("wf-010", "Second version.", report_dir=temp_report_dir)

        result = await read_report("wf-010", report_dir=temp_report_dir)
        assert result["success"] is True
        assert "Second version" in result["content"]

    @pytest.mark.asyncio
    async def test_read_report_not_found(self, temp_report_dir: Path) -> None:
        """read_report returns error when workflow has no reports."""
        result = await read_report("nonexistent", report_dir=temp_report_dir)
        assert result["success"] is False
        assert "not found" in result.get("error", "").lower() or "no reports" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_read_report_directory_not_exist(self) -> None:
        """read_report handles non-existent directory gracefully."""
        result = await read_report("wf-xxx", report_dir=Path("/nonexistent/path/12345"))
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_read_report_parses_frontmatter(self, temp_report_dir: Path) -> None:
        """read_report correctly parses YAML frontmatter."""
        await save_report(
            "wf-011",
            "Body content here.",
            metadata={"title": "My Report", "version": "1.0"},
            report_dir=temp_report_dir,
        )

        result = await read_report("wf-011", report_dir=temp_report_dir)
        assert result["success"] is True
        assert "Body content here" in result["content"]
        assert result["metadata"]["title"] == "My Report"
        assert result["metadata"]["version"] == "1.0"


# ---------------------------------------------------------------------------
# list_versions tests
# ---------------------------------------------------------------------------


class TestListVersions:
    """Verify version listing."""

    @pytest.mark.asyncio
    async def test_list_versions_empty(self, temp_report_dir: Path) -> None:
        """list_versions returns empty list when no reports exist."""
        result = await list_versions("no-reports", report_dir=temp_report_dir)
        assert result["success"] is True
        assert result["versions"] == []

    @pytest.mark.asyncio
    async def test_list_versions_with_reports(self, temp_report_dir: Path) -> None:
        """list_versions returns all versions sorted by newest first."""
        await save_report("wf-020", "V1", report_dir=temp_report_dir)
        import asyncio
        await asyncio.sleep(0.02)  # Ensure unique timestamp
        await save_report("wf-020", "V2", report_dir=temp_report_dir)

        result = await list_versions("wf-020", report_dir=temp_report_dir)
        assert result["success"] is True
        assert len(result["versions"]) == 2
        # Each version has filename, size_bytes, modified_at
        for v in result["versions"]:
            assert "filename" in v
            assert "size_bytes" in v


# ---------------------------------------------------------------------------
# delete_report tests
# ---------------------------------------------------------------------------


class TestDeleteReport:
    """Verify report deletion."""

    @pytest.mark.asyncio
    async def test_delete_all_versions(self, temp_report_dir: Path) -> None:
        """delete_report without version deletes all versions."""
        await save_report("wf-030", "Content", report_dir=temp_report_dir)
        import asyncio
        await asyncio.sleep(0.02)  # Win precision: ~16ms tick, ensure unique timestamp
        await save_report("wf-030", "Content 2", report_dir=temp_report_dir)

        result = await delete_report("wf-030", report_dir=temp_report_dir)
        assert result["success"] is True
        assert result["deleted_count"] == 2

        # Verify no files remain
        remaining = list(temp_report_dir.glob("wf-030_*.md"))
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_workflow(self, temp_report_dir: Path) -> None:
        """Deleting non-existent workflow returns 0 deleted."""
        result = await delete_report("no-such-wf", report_dir=temp_report_dir)
        assert result["success"] is True
        assert result["deleted_count"] == 0


# ---------------------------------------------------------------------------
# Tool callable interface tests
# ---------------------------------------------------------------------------


class TestToolCallables:
    """Verify registry-compatible callable interface."""

    @pytest.mark.asyncio
    async def test_save_report_tool(self, temp_report_dir: Path) -> None:
        """save_report_tool accepts arguments dict."""
        with patch("mcp_tools.internal_tools.file_manager.save_report") as mock_save:
            mock_save.return_value = {"success": True, "filepath": "/tmp/test.md"}
            result = await save_report_tool({
                "workflow_id": "wf-100",
                "content": "Test",
                "metadata": {"title": "T"},
            })
            assert result["success"] is True
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_report_tool(self, temp_report_dir: Path) -> None:
        """read_report_tool accepts arguments dict."""
        with patch("mcp_tools.internal_tools.file_manager.read_report") as mock_read:
            mock_read.return_value = {"success": True, "content": "data"}
            result = await read_report_tool({
                "workflow_id": "wf-200",
                "version": None,
            })
            assert result["success"] is True
            mock_read.assert_called_once()


# ---------------------------------------------------------------------------
# Error type tests
# ---------------------------------------------------------------------------


class TestFileManagerError:
    """Verify error hierarchy."""

    def test_file_manager_error_is_exception(self) -> None:
        assert issubclass(FileManagerError, Exception)
