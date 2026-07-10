"""Models package — LLM clients, router, parsers, and prompt management."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Router (core, always available) ────────────────────────────────────

from models.router import ModelRouter, ModelTier, CircuitState, router

# ── LLM Provider clients ───────────────────────────────────────────────

try:
    from models.llm_providers.deepseek_client import DeepSeekClient
    from models.llm_providers.qwen_client import QwenClient
except ImportError as exc:
    logger.warning("LLM provider clients not available: %s", exc)
    DeepSeekClient = None  # type: ignore[misc,assignment]
    QwenClient = None  # type: ignore[misc,assignment]

# ── JSON parsers ────────────────────────────────────────────────────────

try:
    from models.parsers.json_parser import JSONParser, JSONParseError
    from models.parsers.retry_parser import RetryParser, RetryExhaustedError
except ImportError as exc:
    logger.warning("JSON parsers not available: %s", exc)
    JSONParser = None  # type: ignore[misc,assignment]
    JSONParseError = None  # type: ignore[misc,assignment]
    RetryParser = None  # type: ignore[misc,assignment]
    RetryExhaustedError = None  # type: ignore[misc,assignment]

# ── Prompt manager ──────────────────────────────────────────────────────

try:
    from models.prompts.prompt_manager import PromptManager
except ImportError as exc:
    logger.warning("PromptManager not available: %s", exc)
    PromptManager = None  # type: ignore[misc,assignment]

try:
    from models.prompts.prompt_manager import prompt_manager  # type: ignore[attr-defined]
except ImportError as exc:
    logger.warning("prompt_manager singleton not available: %s", exc)
    prompt_manager = None  # type: ignore[misc,assignment]

# ── Public API ──────────────────────────────────────────────────────────

__all__ = [
    "ModelRouter",
    "ModelTier",
    "CircuitState",
    "router",
    "DeepSeekClient",
    "QwenClient",
    "JSONParser",
    "JSONParseError",
    "RetryParser",
    "RetryExhaustedError",
    "PromptManager",
    "prompt_manager",
]
