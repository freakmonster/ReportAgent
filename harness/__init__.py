"""Harness package — governance layer with Chain of Responsibility pattern.

Architecture (AGENTS.md §1.1):
- All security/validation logic is split into independent Handlers under handlers/
- Orchestrator dynamically loads the chain from config/handler_chain.yaml
- ABSOLUTELY NO hardcoded if/elif chains in the orchestrator
"""

from __future__ import annotations
