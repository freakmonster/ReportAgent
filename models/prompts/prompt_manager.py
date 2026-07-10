"""Prompt manager with Jinja2 template rendering, version hashing, and hot-reload.

Supports V2.1 version hash pinning: each workflow execution binds to a specific
template version via SHA256 hash, protecting in-flight requests from hot-reload
changes.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)


class PromptManager:
    """Manage Jinja2 prompt templates with version hashing and hot-reload.

    Templates are loaded from a directory and rendered with keyword arguments.
    Version hashing ensures deterministic outputs for a given template version.
    """

    def __init__(self, templates_dir: Path) -> None:
        """Initialize the prompt manager.

        Args:
            templates_dir: Directory containing .jinja2 template files.
        """
        self._templates_dir = Path(templates_dir)
        if not self._templates_dir.is_dir():
            raise ValueError(f"Templates directory not found: {self._templates_dir}")

        self._env = Environment(
            loader=FileSystemLoader(str(self._templates_dir)),
            autoescape=False,
        )
        # Cache: template_name → template content (for hash stability across reloads)
        self._content_cache: dict[str, str] = {}
        self._hash_cache: dict[str, str] = {}
        self._preload()

    def _preload(self) -> None:
        """Load all .jinja2 templates and pre-calculate hashes."""
        for tmpl_path in self._templates_dir.glob("*.jinja2"):
            name = tmpl_path.stem
            content = tmpl_path.read_text(encoding="utf-8")
            self._content_cache[name] = content
            self._hash_cache[name] = self._compute_hash(content)

    # ── Public API ──────────────────────────────────────────────────

    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a template with the given keyword arguments.

        Args:
            template_name: Name of the template file without extension
                           (e.g. "researcher" for "researcher.jinja2").
            **kwargs: Variables to pass into the template context.

        Returns:
            The rendered template string.

        Raises:
            jinja2.TemplateNotFound: If template_name does not exist.
        """
        template: Template = self._env.get_template(f"{template_name}.jinja2")
        return template.render(**kwargs)

    def get_version_hash(self, template_name: str) -> str:
        """Get the SHA256 version hash for a template.

        Args:
            template_name: Name of the template (without extension).

        Returns:
            Hexadecimal SHA256 digest of the template content.

        Raises:
            KeyError: If the template is not loaded.
        """
        if template_name in self._hash_cache:
            return self._hash_cache[template_name]

        # Fallback: compute on-the-fly
        tmpl_path = self._templates_dir / f"{template_name}.jinja2"
        if not tmpl_path.exists():
            raise KeyError(f"Template not found: {template_name}")
        content = tmpl_path.read_text(encoding="utf-8")
        return self._compute_hash(content)

    def reload(self) -> None:
        """Reload all templates from disk (hot-reload).

        Clears the Jinja2 template cache and re-reads all template files.
        New hashes are computed for changed templates. In-flight requests
        that pinned a specific hash are NOT affected.
        """
        self._env = Environment(
            loader=FileSystemLoader(str(self._templates_dir)),
            autoescape=False,
        )
        self._content_cache.clear()
        self._hash_cache.clear()
        self._preload()
        logger.info("prompt_manager.reloaded", template_count=len(self._content_cache))

    def list_templates(self) -> list[str]:
        """List all available template names.

        Returns:
            Sorted list of template names (without .jinja2 extension).
        """
        return sorted(self._content_cache.keys())

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA256 hex digest of template content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
