"""DeepSeek API async client wrapper using OpenAI-compatible SDK.

Features:
- Async chat completion with streaming support
- Exponential backoff retry via tenacity
- Retries on APIError and APITimeoutError (max 3 attempts)
"""

from __future__ import annotations

import logging
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Retry configuration ──────────────────────────────────────────────

_RETRYABLE = (APIError, APITimeoutError)


def _log_retry(retry_state: Any) -> None:
    """Log retry attempts for observability."""
    logger.warning(
        "DeepSeek API retry attempt %d/%d (exception: %s)",
        retry_state.attempt_number,
        3,
        retry_state.outcome.exception() if retry_state.outcome else "N/A",
    )


# ── Model Tier Mapping ────────────────────────────────────────────────

_DEEPSEEK_TIER_MAP: dict[str, str] = {
    "pro": "deepseek-v4-pro",
    "flash": "deepseek-v4-flash",
}


# ── Client ───────────────────────────────────────────────────────────


class DeepSeekClient:
    """Async client for DeepSeek API (OpenAI-compatible)."""

    def __init__(self, tier: str | None = None) -> None:
        self._api_key: str = settings.deepseek_api_key
        self._base_url: str = settings.deepseek_base_url
        if tier:
            resolved = _DEEPSEEK_TIER_MAP.get(tier)
            if resolved:
                self._model: str = resolved
            else:
                logger.warning(
                    "Unknown DeepSeek tier '%s', falling back to '%s'",
                    tier,
                    settings.deepseek_model,
                )
                self._model = settings.deepseek_model
        else:
            self._model = settings.deepseek_model
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazily create the AsyncOpenAI client on first use."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=30),
        before_sleep=_log_retry,
    )
    async def _chat_raw(
        self, messages: list[dict[str, Any]], temperature: float, max_tokens: int, **kwargs: Any
    ) -> dict[str, Any]:
        """Raw API call with tenacity retry — called by chat() after cache check."""
        response = await self._get_client().chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.model_dump()

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Send a chat completion request with semantic caching.

        Cache hit → returns immediately (no API call).
        Cache miss → retry-wrapped API call → store in cache.

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
        result = await self._chat_raw(messages, temperature, max_tokens, **kwargs)

        # ── Store in cache (fire-and-forget, non-blocking) ──
        import asyncio

        asyncio.create_task(cache_set(messages, result, temperature, max_tokens, self._model))

        # ── Async stats (fire-and-forget) ──
        try:
            asyncio.create_task(_incr_stats(self._model, result))
        except Exception:
            pass

        return result

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=30),
        before_sleep=_log_retry,
    )
    async def chat_stream(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
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
