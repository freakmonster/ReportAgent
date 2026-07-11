"""
Internal file manager — Report file I/O and history versioning.

Handles:
- Reading/writing Markdown research reports
- History version tracking
- Report metadata management

Used by internal tools and as a fallback when MCP services are unavailable.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default report storage directory (inside project root)
DEFAULT_REPORT_DIR: Path = Path(__file__).resolve().parent.parent.parent / "data" / "reports"


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

async def save_report(
    workflow_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    """Save a research report to disk.

    Creates a versioned copy and updates the "latest" symlink/default file.

    Args:
        workflow_id: Unique workflow identifier.
        content: Markdown content of the report.
        metadata: Optional metadata dict (title, author, tags, etc.).
        report_dir: Optional custom directory. Defaults to data/reports/.

    Returns:
        Dict with keys: success, filepath, version, timestamp.
    """
    directory = report_dir or DEFAULT_REPORT_DIR
    os.makedirs(directory, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")
    filename = f"{workflow_id}_{timestamp}.md"
    filepath = directory / filename

    # ── Prepare file content with YAML frontmatter ──────────────────
    meta = metadata or {}
    frontmatter = "---\n"
    frontmatter += f"workflow_id: {workflow_id}\n"
    frontmatter += f"created_at: {timestamp}\n"
    for key, value in meta.items():
        frontmatter += f"{key}: {value}\n"
    frontmatter += "---\n\n"

    try:
        filepath.write_text(frontmatter + content, encoding="utf-8")
        logger.info("Report saved: %s", filepath)
        return {
            "success": True,
            "filepath": str(filepath),
            "filename": filename,
            "workflow_id": workflow_id,
            "timestamp": timestamp,
        }
    except OSError as exc:
        logger.error("Failed to save report %s: %s", workflow_id, exc)
        raise FileManagerError(f"Failed to save report: {exc}") from exc


async def read_report(
    workflow_id: str,
    version: str | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    """Read a saved research report.

    Args:
        workflow_id: The workflow ID to look up.
        version: Optional timestamp version string (e.g. "20260115_143000").
                 If None, returns the latest version.
        report_dir: Optional custom directory.

    Returns:
        Dict with keys: success, content, metadata, filename.
    """
    directory = report_dir or DEFAULT_REPORT_DIR

    if not directory.exists():
        return {"success": False, "error": f"Report directory not found: {directory}"}

    # Find matching files
    pattern = f"{workflow_id}_*.md"
    matches = sorted(directory.glob(pattern), reverse=True)

    if not matches:
        return {
            "success": False,
            "error": f"No reports found for workflow: {workflow_id}",
        }

    if version:
        target = directory / f"{workflow_id}_{version}.md"
        if not target.exists():
            return {
                "success": False,
                "error": f"Version not found: {version}",
            }
        filepath = target
    else:
        filepath = matches[0]  # Latest

    try:
        raw_content = filepath.read_text(encoding="utf-8")

        # Parse frontmatter
        meta = {}
        content = raw_content
        if raw_content.startswith("---"):
            parts = raw_content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        key, _, value = line.partition(":")
                        meta[key.strip()] = value.strip()
                content = parts[2].strip()

        logger.info("Report read: %s", filepath)
        return {
            "success": True,
            "content": content,
            "metadata": meta,
            "filename": filepath.name,
        }
    except OSError as exc:
        logger.error("Failed to read report %s: %s", filepath, exc)
        raise FileManagerError(f"Failed to read report: {exc}") from exc


async def list_versions(
    workflow_id: str,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    """List all saved versions of a report.

    Args:
        workflow_id: The workflow ID to look up.
        report_dir: Optional custom directory.

    Returns:
        Dict with keys: success, workflow_id, versions (list of {filename, timestamp, size}).
    """
    directory = report_dir or DEFAULT_REPORT_DIR

    if not directory.exists():
        return {"success": True, "workflow_id": workflow_id, "versions": []}

    pattern = f"{workflow_id}_*.md"
    matches = sorted(directory.glob(pattern), reverse=True)

    versions: list[dict[str, Any]] = []
    for f in matches:
        stat = f.stat()
        versions.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    return {"success": True, "workflow_id": workflow_id, "versions": versions}


async def delete_report(
    workflow_id: str,
    version: str | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    """Delete a report version (or all versions if version is None).

    Args:
        workflow_id: The workflow ID.
        version: Optional version string. If None, deletes all versions.
        report_dir: Optional custom directory.

    Returns:
        Dict with keys: success, deleted_count.
    """
    directory = report_dir or DEFAULT_REPORT_DIR

    if not directory.exists():
        return {"success": True, "deleted_count": 0}

    if version:
        target = directory / f"{workflow_id}_{version}.md"
        if target.exists():
            target.unlink()
            logger.info("Deleted report version: %s", target)
            return {"success": True, "deleted_count": 1}
        return {"success": True, "deleted_count": 0}

    # Delete all versions
    pattern = f"{workflow_id}_*.md"
    matches = list(directory.glob(pattern))
    count = 0
    for f in matches:
        f.unlink()
        count += 1

    logger.info("Deleted %d report versions for %s", count, workflow_id)
    return {"success": True, "deleted_count": count}


# ---------------------------------------------------------------------------
# Registry-compatible callables
# ---------------------------------------------------------------------------

async def save_report_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    """Registry-compatible callable for saving reports.

    Args:
        arguments: {"workflow_id": str, "content": str, "metadata": dict | None}
    """
    return await save_report(
        workflow_id=arguments["workflow_id"],
        content=arguments["content"],
        metadata=arguments.get("metadata"),
    )


async def read_report_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    """Registry-compatible callable for reading reports.

    Args:
        arguments: {"workflow_id": str, "version": str | None}
    """
    return await read_report(
        workflow_id=arguments["workflow_id"],
        version=arguments.get("version"),
    )


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class FileManagerError(Exception):
    """Raised when a file operation fails."""
