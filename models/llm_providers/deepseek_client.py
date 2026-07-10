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


# ── Client ───────────────────────────────────────────────────────────

class DeepSeekClient:
    """Async client for DeepSeek API (OpenAI-compatible)."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self._model: str = settings.deepseek_model

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=30),
        before_sleep=_log_retry,
    )
    async def chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        """Send a chat completion request with exponential backoff retry.

        Args:
            messages: List of message dicts (role/content).
            **kwargs: Extra parameters forwarded to the API.

        Returns:
            The full chat completion response object as a dict.
        """
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            **kwargs,
        )
        return response.model_dump()

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=30),
        before_sleep=_log_retry,
    )
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
        stream = await self._client.chat.completions.create(
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
