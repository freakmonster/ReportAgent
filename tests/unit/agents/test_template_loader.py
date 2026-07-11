"""Unit tests for workflow template loader."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from agents.workflows.templates.loader import TemplateLoader  # noqa: E402


class TestTemplateLoader:
    """Verify YAML template loading and validation."""

    def test_loads_all_templates(self) -> None:
        loader = TemplateLoader()
        names = loader.template_names
        assert "deep_report" in names
        assert "flash_news" in names
        assert "earnings_analysis" in names

    def test_default_template(self) -> None:
        loader = TemplateLoader()
        assert loader.default_template == "deep_report"

    def test_get_valid_template(self) -> None:
        loader = TemplateLoader()
        tpl = loader.get_template("deep_report")
        assert "nodes" in tpl
        assert "entry_point" in tpl
        assert len(tpl["nodes"]) >= 5

    def test_get_invalid_template_raises(self) -> None:
        loader = TemplateLoader()
        with pytest.raises(ValueError):
            loader.get_template("nonexistent")

    def test_list_templates(self) -> None:
        loader = TemplateLoader()
        templates = loader.list_templates()
        assert len(templates) == 3
        for t in templates:
            assert "name" in t
            assert "node_count" in t

    def test_reload(self) -> None:
        loader = TemplateLoader()
        loader.reload()
        assert loader.template_names  # still loads correctly
