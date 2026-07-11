"""
Permission Handler — role-tool permission matrix validation.

Reads role constraints from config/handler_chain.yaml + role_constraints.yaml.
Enforces that agents cannot call tools outside their authorized set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler


class PermissionHandler(HarnessHandler):
    """Validates that the current node has permission to call requested tools."""

    def __init__(self, constraints_path: str | None = None) -> None:
        self._constraints_path = constraints_path or str(
            Path(__file__).resolve().parent.parent / "constraints" / "role_constraints.yaml"
        )
        self._constraints: dict[str, Any] = {}
        self._load_constraints()

    def _load_constraints(self) -> None:
        """Load role constraints from YAML file."""
        try:
            path = Path(self._constraints_path)
            if path.exists():
                self._constraints = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            self._constraints = {}

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Check if the requested tools are within the agent's permission set."""
        from harness.orchestrator.context import PreExecContext

        if not isinstance(pre_ctx, PreExecContext):
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No pre-exec context, skipping permission check",
            )

        node_name = pre_ctx.node_name
        tool_permissions = pre_ctx.tool_permissions

        # If no tool permissions are set, we can't check — pass through
        if not tool_permissions:
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail="No tool permissions defined for this execution",
            )

        # Check if this node has specific constraints
        node_constraints = self._constraints.get("nodes", {}).get(node_name, {})

        # Allowed tools for this node (union of YAML constraints + permissions context)
        allowed_tools: set[str] = set(node_constraints.get("allowed_tools", []))
        if not allowed_tools:
            # No explicit constraints → all tools allowed
            return HandlerResult(
                decision=HandlerDecision.PASS,
                detail=f"No tool restrictions for node '{node_name}'",
            )

        # Check each requested tool against allowed list
        denied: list[str] = []
        for tool_name, is_allowed in tool_permissions.items():
            if not is_allowed and tool_name not in allowed_tools:
                denied.append(tool_name)

        if denied:
            return HandlerResult(
                decision=HandlerDecision.REJECT,
                detail=f"Node '{node_name}' is not authorized to use tools: {', '.join(denied)}",
                metrics={"denied_tools": denied, "allowed_tools": sorted(allowed_tools)},
            )

        return HandlerResult(
            decision=HandlerDecision.PASS,
            detail=f"Permission check passed for node '{node_name}'",
            metrics={"checked_tools": len(tool_permissions)},
        )
