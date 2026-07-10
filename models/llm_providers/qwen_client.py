"""Qwen API async client wrapper using OpenAI-compatible SDK.

Features:
- Async chat completion with streaming support
- Multi-size model support: 1.8B (light), 7B (medium), Max (heavy)
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Model size mapping ───────────────────────────────────────────────

_MODEL_SIZE_MAP: dict[str, str] = {
    "1.8b": settings.qwen_light_model,
    "7b": settings.qwen_medium_model,
    "max": settings.qwen_model,
}


# ── Client ───────────────────────────────────────────────────────────

class QwenClient:
    """Async client for Qwen API (OpenAI-compatible)."""

    def __init__(self, model_size: str = "max") -> None:
        """Initialise the Qwen client.

        Args:
            model_size: One of "1.8b", "7b", or "max".  Defaults to "max".
        """
        resolved: str | None = _MODEL_SIZE_MAP.get(model_size)
        if resolved is None:
            logger.warning(
                "Unknown model_size '%s', falling back to 'max'", model_size
            )
            resolved = settings.qwen_model

        self._client: AsyncOpenAI = AsyncOpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        )
        self._model: str = resolved

    async def chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        """Send a chat completion request.

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
