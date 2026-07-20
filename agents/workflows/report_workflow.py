"""Report workflow — lightweight helper functions only.

AGENTS.md §1.2: 主体逻辑由 builder 注入，本模块仅保留通用辅助函数。
No edge definitions or node ordering hardcoded here.
"""

from __future__ import annotations

from typing import Any


def increment_retry(state: dict[str, Any]) -> dict[str, Any]:
    """Increment retry_count in base context (helper for writer retry loop)."""
    base = state.get("base", {})
    if isinstance(base, dict):
        base["retry_count"] = base.get("retry_count", 0) + 1
    return {"base": base}


def get_template_name(state: dict[str, Any]) -> str:
    """Extract template name from state."""
    base = state.get("base", {})
    return (
        str(base.get("template_name", "deep_report")) if isinstance(base, dict) else "deep_report"
    )
