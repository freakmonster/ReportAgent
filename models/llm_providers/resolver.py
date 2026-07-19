"""LLM client resolver — maps model string to provider client instance.

Centralised factory so writer / data_analyst / any LLM-using node can
resolve the model from state without duplicating the provider logic.
"""

from __future__ import annotations

from typing import Any


def resolve_llm_client(model: str) -> Any:
    """Resolve a model string to the appropriate async LLM client.

    Args:
        model: One of deepseek-flash, deepseek-pro, qwen-8b, qwen-32b, qwen-max.

    Returns:
        DeepSeekClient or QwenClient instance ready for chat() calls.
    """
    if model.startswith("qwen"):
        from models.llm_providers.qwen_client import QwenClient
        # qwen-8b → 8b, qwen-32b → 32b, qwen-max → max
        size = model.split("-", 1)[1] if "-" in model else "max"
        return QwenClient(model_size=size)

    # deepseek-flash / deepseek-pro
    from models.llm_providers.deepseek_client import DeepSeekClient
    tier = model.split("-", 1)[1] if "-" in model else "flash"
    return DeepSeekClient(tier=tier)
