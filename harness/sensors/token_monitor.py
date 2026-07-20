"""
Token Monitor — real-time token consumption tracking and cost alert.

Tracks total tokens consumed across all nodes and warns when approaching
configured thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenUsage:
    """Token consumption record for a single node execution."""

    node_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def estimated_cost(self) -> float:
        """Estimate cost in USD (approximate DeepSeek pricing)."""
        prompt_cost = (self.prompt_tokens / 1_000_000) * 0.14  # $0.14/M input
        completion_cost = (self.completion_tokens / 1_000_000) * 0.28  # $0.28/M output
        return round(prompt_cost + completion_cost, 6)


class TokenMonitor:
    """Tracks token consumption across workflow execution.

    Features:
    - Per-node usage tracking
    - Cumulative totals
    - Cost estimation
    - Threshold-based warnings
    """

    WARNING_THRESHOLD: int = 100_000  # Warn when total exceeds 100K
    CRITICAL_THRESHOLD: int = 500_000  # Alert at 500K tokens

    def __init__(self) -> None:
        self._usage: list[TokenUsage] = []
        self._warnings_issued: int = 0

    def record(
        self,
        node_name: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record token usage for a node execution.

        Args:
            node_name: Name of the node that consumed tokens.
            prompt_tokens: Input tokens used.
            completion_tokens: Output tokens generated.
        """
        usage = TokenUsage(
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        self._usage.append(usage)

    @property
    def total_tokens(self) -> int:
        """Cumulative tokens consumed."""
        return sum(u.total_tokens for u in self._usage)

    @property
    def total_cost(self) -> float:
        """Cumulative estimated cost in USD."""
        return round(sum(u.estimated_cost for u in self._usage), 6)

    def check_thresholds(self) -> dict[str, Any]:
        """Check if token usage exceeds warning/critical thresholds.

        Returns:
            Dict with status, total_tokens, total_cost, and alert_level.
        """
        total = self.total_tokens
        if total >= self.CRITICAL_THRESHOLD:
            return {
                "status": "critical",
                "total_tokens": total,
                "total_cost": self.total_cost,
                "alert_level": "CRITICAL",
                "message": f"Token usage {total} exceeds critical threshold {self.CRITICAL_THRESHOLD}",
            }
        if total >= self.WARNING_THRESHOLD:
            return {
                "status": "warning",
                "total_tokens": total,
                "total_cost": self.total_cost,
                "alert_level": "WARNING",
                "message": f"Token usage {total} exceeds warning threshold {self.WARNING_THRESHOLD}",
            }
        return {
            "status": "ok",
            "total_tokens": total,
            "total_cost": self.total_cost,
            "alert_level": "OK",
        }

    def get_per_node_summary(self) -> list[dict[str, Any]]:
        """Return per-node token usage summary."""
        result: list[dict[str, Any]] = []
        for u in self._usage:
            result.append(
                {
                    "node": u.node_name,
                    "tokens": u.total_tokens,
                    "cost": u.estimated_cost,
                }
            )
        return result

    def reset(self) -> None:
        """Reset all tracking data."""
        self._usage.clear()
        self._warnings_issued = 0
