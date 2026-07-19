"""Qwen API async client wrapper using OpenAI-compatible SDK.

Features:
- Async chat completion with streaming support
- Multi-size model support: 8B (light), 32B (medium), Max (heavy)
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Model size mapping ───────────────────────────────────────────────

_MODEL_SIZE_MAP: dict[str, str] = {
    "8b": settings.qwen_light_model,
    "32b": settings.qwen_medium_model,
    "max": settings.qwen_model,
}


# ── Client ───────────────────────────────────────────────────────────

class QwenClient:
    """Async client for Qwen API (OpenAI-compatible)."""

    def __init__(self, model_size: str = "max") -> None:
        """Initialise the Qwen client.

        Args:
            model_size: One of "8b", "32b", or "max".  Defaults to "max".
        """
        resolved: str | None = _MODEL_SIZE_MAP.get(model_size)
        if resolved is None:
            logger.warning(
                "Unknown model_size '%s', falling back to 'max'", model_size
            )
            resolved = settings.qwen_model

        self._api_key: str = settings.qwen_api_key
        self._base_url: str = settings.qwen_base_url
        self._model: str = resolved
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazily create the AsyncOpenAI client on first use."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        """Send a chat completion request with semantic caching.

        Cache hit → returns immediately (no API call).
        Cache miss → API call → store in cache.

        Args:
            messages: List of message dicts (role/content).
            **kwargs: Extra parameters forwarded to the API.
                temperature (default 0.7), max_tokens (default 2048).

        Returns:
            The full chat completion response object as a dict.
        """
        temperature: float = float(kwargs.pop("temperature", 0.7))
        max_tokens: int = int(kwargs.pop("max_tokens", 2048))

        # ── Check semantic cache ──
        from models.semantic_cache import cache_get, cache_set

        cached = await cache_get(messages, temperature, max_tokens, self._model)
        if cached is not None:
            return cached

        # ── Cache miss: make real API call ──
        response = await self._get_client().chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={"enable_thinking": False},  # required for non-streaming qwen-max
            **kwargs,
        )
        result = response.model_dump()

        # ── Store in cache (fire-and-forget, non-blocking) ──
        import asyncio
        asyncio.create_task(
            cache_set(messages, result, temperature, max_tokens, self._model)
        )

        # ── Async stats (fire-and-forget) ──
        try:
            asyncio.create_task(_incr_stats(self._model, result))
        except Exception:
            pass

        return result

    async def chat_stream(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> Any:
        """Stream chat completion chunks.

        Args:
            messages: List of message dicts (role/content).
            **kwargs: Extra parameters forwarded to the API.

        Yields:
            Each chunk as a dict from the streaming response.
        """
        stream = await self._get_client().chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            yield chunk.model_dump()

    @property
    def model(self) -> str:
        """Return the configured model name."""
        return self._model


# ── Stats helper ──────────────────────────────────────────────────────


async def _incr_stats(model: str, result: dict[str, Any]) -> None:
    """Fire-and-forget stats recording for a successful API call."""
    try:
        from infrastructure.memory.stats import incr_llm_request, incr_llm_tokens

        usage: dict[str, int] = result.get("usage", {})
        total_tokens: int = usage.get("total_tokens", 0)
        await incr_llm_request(model)
        if total_tokens:
            await incr_llm_tokens(model, total_tokens)
    except Exception:
        pass
