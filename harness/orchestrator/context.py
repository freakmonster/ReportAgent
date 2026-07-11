"""
Harness orchestration context — data carriers for pre/post execution.

PreExecContext: snapshot before a LangGraph node runs
PostExecContext: snapshot after a LangGraph node completes
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PreExecContext:
    """Context captured before a LangGraph node executes.

    Attributes:
        node_name: Name of the node about to execute (e.g. 'writer')
        raw_input: The raw user input string
        user_id: Current user identifier
        tool_permissions: Dict of tool_name → allowed (bool)
        state_snapshot: Shallow copy of the LangGraph state at this point
        timestamp: When the context was created (epoch seconds)
    """
    node_name: str = ""
    raw_input: str = ""
    user_id: str = ""
    tool_permissions: dict[str, bool] = field(default_factory=dict)
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PostExecContext:
    """Context captured after a LangGraph node completes.

    Attributes:
        node_name: Name of the node that just executed
        raw_output: The raw output produced by the node
        state_snapshot: Shallow copy of the LangGraph state after execution
        duration_ms: Node execution time in milliseconds
        token_usage: Estimated token count used (filled by token_monitor)
    """
    node_name: str = ""
    raw_output: str = ""
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    token_usage: int = 0
