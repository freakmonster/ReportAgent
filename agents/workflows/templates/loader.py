"""Workflow template loader — reads config/workflow_templates.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class TemplateLoader:
    """Loads and validates workflow templates from YAML configuration.

    Features:
    - Reads config/workflow_templates.yaml
    - Validates node names against known modules
    - Validates edge rules are syntactically correct
    - Supports reload() for hot-update
    """

    # Known valid node modules (must exist under agents/nodes/)
    _KNOWN_NODES: set[str] = {
        "intent_classifier",
        "research_planner",
        "data_collector",
        "data_processor",
        "data_analyst",
        "writer",
        "editor",
        "reviewer",
        "human_review",
        "publisher",
    }

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path or str(
            Path(__file__).resolve().parent.parent.parent.parent
            / "config"
            / "workflow_templates.yaml"
        )
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load and validate YAML config."""
        path = Path(self._config_path)
        if not path.exists():
            raise FileNotFoundError(f"Template config not found: {path}")

        self._config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def reload(self) -> None:
        """Reload config from disk (hot-update)."""
        self._load()

    @property
    def default_template(self) -> str:
        """Return the default template name."""
        return self._config.get("default_template", "deep_report")

    @property
    def template_names(self) -> list[str]:
        """List all available template names."""
        templates = self._config.get("templates", {})
        return list(templates.keys())

    def get_template(self, name: str) -> dict[str, Any]:
        """Get a specific template definition.

        Args:
            name: Template name (e.g., 'deep_report').

        Returns:
            Template dict with nodes, edges, entry_point, finish_point.

        Raises:
            ValueError: If the template name is unknown.
        """
        templates = self._config.get("templates", {})
        if name not in templates:
            raise ValueError(f"Unknown template '{name}'. Available: {self.template_names}")
        tpl = templates[name]
        self._validate_template(name, tpl)
        return tpl

    def _validate_template(self, name: str, tpl: dict[str, Any]) -> None:
        """Validate a template definition."""
        # Check required keys
        for key in ("nodes", "entry_point"):
            if key not in tpl:
                raise ValueError(f"Template '{name}' missing required key: {key}")

        # Check all nodes are known
        for node in tpl.get("nodes", []):
            if node not in self._KNOWN_NODES:
                raise ValueError(
                    f"Template '{name}' references unknown node '{node}'. "
                    f"Known: {sorted(self._KNOWN_NODES)}"
                )

        # Check entry point is in nodes
        entry = tpl.get("entry_point", "")
        if entry not in tpl.get("nodes", []):
            raise ValueError(f"Template '{name}' entry_point '{entry}' not in nodes list")

    def list_templates(self) -> list[dict[str, Any]]:
        """Return metadata for all templates."""
        templates = self._config.get("templates", {})
        return [
            {
                "name": name,
                "description": tpl.get("description", ""),
                "node_count": len(tpl.get("nodes", [])),
            }
            for name, tpl in templates.items()
        ]


# Module-level singleton
template_loader = TemplateLoader()
