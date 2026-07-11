"""
Audit Handler — full-chain trace logging (always last in the chain).

Records:
- Input/output snapshots for every node execution
- Execution duration and token consumption
- Handler chain results (PASS / FAIL / REJECT)

This handler is ALWAYS placed last in the YAML chain to guarantee
it runs regardless of prior handler results.
"""

from __future__ import annotations

import json
import time
from typing import Any

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler


class AuditHandler(HarnessHandler):
    """Records complete audit trail for every node execution.

    Always returns PASS — audit logging should never block execution.
    """

    def __init__(self) -> None:
        self._audit_log: list[dict[str, Any]] = []
        self._start_time: float = 0.0

    async def handle(
        self,
        pre_ctx: object,
        post_ctx: object,
    ) -> HandlerResult:
        """Record audit log entry for the current node execution."""
        from harness.orchestrator.context import PostExecContext, PreExecContext

        entry: dict[str, Any] = {
            "timestamp": time.time(),
            "handler_name": self.name,
        }

        if isinstance(pre_ctx, PreExecContext):
            entry["node_name"] = pre_ctx.node_name
            entry["user_id"] = pre_ctx.user_id
            entry["input_length"] = len(pre_ctx.raw_input)

        if isinstance(post_ctx, PostExecContext):
            entry["output_length"] = len(post_ctx.raw_output)
            entry["duration_ms"] = post_ctx.duration_ms
            entry["token_usage"] = post_ctx.token_usage

        self._audit_log.append(entry)

        return HandlerResult(
            decision=HandlerDecision.PASS,
            detail="Audit log recorded",
            metrics={"audit_entry_id": len(self._audit_log)},
        )

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return the accumulated audit log (for testing/export)."""
        return list(self._audit_log)

    def get_log_as_json(self) -> str:
        """Export the audit log as JSON string."""
        return json.dumps(self._audit_log, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        """Clear the accumulated audit log."""
        self._audit_log.clear()
