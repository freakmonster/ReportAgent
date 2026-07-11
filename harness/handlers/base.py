"""
Harness handler abstract base class — Chain of Responsibility pattern.

All governance checks (input safety, permission, fact checking, etc.) MUST
implement this interface.  The orchestrator loads handlers from YAML config
and calls them sequentially without knowing their concrete types.

AGENTS.md §1.1: 严禁在 orchestrator 中使用 if isinstance(handler, ...) 硬编码判断。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HandlerDecision(str, Enum):
    """Decision returned by a handler after checking pre/post context."""
    PASS = "pass"        # All clear, continue to next handler
    FAIL = "fail"        # Issue found but not critical (warning-level, continue)
    REJECT = "reject"    # Critical issue, short-circuit the chain immediately


@dataclass
class HandlerResult:
    """Result returned by a HarnessHandler.handle() call.

    Attributes:
        decision: PASS (continue), FAIL (warning), or REJECT (stop chain)
        detail: Human-readable explanation of the decision
        metrics: Arbitrary key-value data for observability (timing, counts, etc.)
        handler_name: Automatically set by the orchestrator
    """
    decision: HandlerDecision
    detail: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    handler_name: str = ""


class HarnessHandler(ABC):
    """Abstract base class for all governance handlers.

    Subclasses must implement:
        async handle(pre_ctx, post_ctx) -> HandlerResult

    The orchestrator calls handle() for each handler in the configured chain.
    If any handler returns REJECT, the chain short-circuits.
    If any returns FAIL, the chain continues but the result is recorded.
    """

    @abstractmethod
    async def handle(
        self,
        pre_ctx: object,   # PreExecContext (from harness.orchestrator.context)
        post_ctx: object,  # PostExecContext
    ) -> HandlerResult:
        """Execute governance check.

        Args:
            pre_ctx: Context before node execution (input, user, permissions).
            post_ctx: Context after node execution (output, state snapshot).

        Returns:
            HandlerResult with PASS / FAIL / REJECT decision.
        """
        ...

    @property
    def name(self) -> str:
        """Handler name for logging and YAML configuration."""
        return self.__class__.__name__
