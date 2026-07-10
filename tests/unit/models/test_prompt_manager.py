"""Unit tests for PromptManager — template rendering, version hashing, and hot-reload."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from models.prompts.prompt_manager import PromptManager  # noqa: E402


@pytest.fixture
def templates_dir() -> str:
    """Create a temporary directory with sample Jinja2 templates.

    Returns the path as a string to be easily closed after test.
    """
    tmpdir = tempfile.mkdtemp()
    base = Path(tmpdir)

    # Researcher template
    (base / "researcher.jinja2").write_text(
        (
            "You are a senior researcher. Query: {{ query }}.\n"
            "Please provide detailed analysis on {{ topic }}."
        ),
        encoding="utf-8",
    )

    # Writer template
    (base / "writer.jinja2").write_text(
        (
            "You are a professional writer.\n"
            "Chapter: {{ chapter_title }}\n"
            "Data: {{ chapter_data }}"
        ),
        encoding="utf-8",
    )

    # Reviewer template
    (base / "reviewer.jinja2").write_text(
        (
            "You are a rigorous reviewer.\n"
            "Report: {{ report_content }}\n"
            "Output as JSON: {\"verdict\": \"{{ verdict }}\"}"
        ),
        encoding="utf-8",
    )

    return str(base)


# ── Render tests ──────────────────────────────────────────────────────


def test_render_researcher_template(templates_dir: str) -> None:
    """Verify researcher.jinja2 renders correctly with a query."""
    pm = PromptManager(Path(templates_dir))
    result = pm.render("researcher", query="EV market analysis", topic="new energy vehicles")

    assert "EV market analysis" in result
    assert "new energy vehicles" in result
    assert "senior researcher" in result.lower()


def test_render_writer_template(templates_dir: str) -> None:
    """Verify writer.jinja2 renders with chapter data."""
    pm = PromptManager(Path(templates_dir))
    result = pm.render(
        "writer",
        chapter_title="Market Overview",
        chapter_data="The EV market grew 45% YoY.",
    )

    assert "Market Overview" in result
    assert "45% YoY" in result
    assert "professional writer" in result.lower()


def test_render_reviewer_template(templates_dir: str) -> None:
    """Verify reviewer.jinja2 renders and contains JSON structure."""
    pm = PromptManager(Path(templates_dir))
    result = pm.render(
        "reviewer",
        report_content="Sample report text",
        verdict="approved",
    )

    assert "rigorous reviewer" in result.lower()
    assert "Sample report text" in result
    assert '"verdict": "approved"' in result
    assert "Output as JSON" in result


# ── Version hash tests ────────────────────────────────────────────────


def test_version_hash_consistency(templates_dir: str) -> None:
    """Verify the same template content produces the same hash."""
    pm = PromptManager(Path(templates_dir))
    hash1 = pm.get_version_hash("researcher")
    hash2 = pm.get_version_hash("researcher")

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex digest length
    assert hash1 == hashlib.sha256(
        (Path(templates_dir) / "researcher.jinja2").read_text("utf-8").encode("utf-8")
    ).hexdigest()


def test_version_hash_changes_on_content_update(templates_dir: str) -> None:
    """Verify different content produces different hash."""
    pm = PromptManager(Path(templates_dir))
    hash_before = pm.get_version_hash("writer")

    # Modify the template
    writer_path = Path(templates_dir) / "writer.jinja2"
    writer_path.write_text("Completely different content for writer.", encoding="utf-8")

    pm.reload()
    hash_after = pm.get_version_hash("writer")

    assert hash_before != hash_after


def test_different_templates_have_different_hashes(templates_dir: str) -> None:
    """Verify different template files produce different hashes."""
    pm = PromptManager(Path(templates_dir))
    researcher_hash = pm.get_version_hash("researcher")
    writer_hash = pm.get_version_hash("writer")
    reviewer_hash = pm.get_version_hash("reviewer")

    assert researcher_hash != writer_hash
    assert writer_hash != reviewer_hash
    assert researcher_hash != reviewer_hash


# ── Hot-reload tests ──────────────────────────────────────────────────


def test_reload_updates_templates(templates_dir: str) -> None:
    """Verify reload() picks up modified template content."""
    pm = PromptManager(Path(templates_dir))

    # First render with original content
    result1 = pm.render("researcher", query="test", topic="topic")
    assert "test" in result1

    # Modify the template file directly
    researcher_path = Path(templates_dir) / "researcher.jinja2"
    researcher_path.write_text("Updated template: {{ query }} only.", encoding="utf-8")

    # Reload
    pm.reload()

    # Render again — should use new content
    result2 = pm.render("researcher", query="test2", topic="topic")

    assert "Updated template" in result2
    assert "test2" in result2


def test_reload_updates_hash(templates_dir: str) -> None:
    """Verify reload() updates the version hash for modified templates."""
    pm = PromptManager(Path(templates_dir))
    hash_before = pm.get_version_hash("researcher")

    # Modify template
    (Path(templates_dir) / "researcher.jinja2").write_text(
        "Modified content for hash test.", encoding="utf-8"
    )
    pm.reload()
    hash_after = pm.get_version_hash("researcher")

    assert hash_before != hash_after


# ── Edge case tests ───────────────────────────────────────────────────


def test_list_templates(templates_dir: str) -> None:
    """Verify list_templates() returns all template names."""
    pm = PromptManager(Path(templates_dir))
    templates = pm.list_templates()

    assert "researcher" in templates
    assert "writer" in templates
    assert "reviewer" in templates
    assert len(templates) == 3


def test_missing_template_raises_key_error(templates_dir: str) -> None:
    """Verify get_version_hash raises KeyError for missing template."""
    pm = PromptManager(Path(templates_dir))
    with pytest.raises(KeyError, match="Template not found"):
        pm.get_version_hash("nonexistent")


def test_nonexistent_directory_raises() -> None:
    """Verify ValueError is raised if templates_dir doesn't exist."""
    with pytest.raises(ValueError, match="Templates directory not found"):
        PromptManager(Path("/nonexistent/path/for/templates"))
