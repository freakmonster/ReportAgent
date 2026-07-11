"""Unit tests for DeepSeekClient — async calls, streaming, and retry logic."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import httpx  # noqa: E402
import pytest  # noqa: E402
from openai import APIError  # noqa: E402
from tenacity import RetryError  # noqa: E402

from models.llm_providers.deepseek_client import DeepSeekClient  # noqa: E402


@pytest.mark.asyncio
async def test_chat_success(
    mock_openai_response: MagicMock,
    sample_messages: list[dict[str, str]],
) -> None:
    """Verify that chat() returns the correct response on a successful API call."""
    with patch(
        "models.llm_providers.deepseek_client.AsyncOpenAI"
    ) as mock_async_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
        mock_async_openai.return_value = mock_client

        client = DeepSeekClient()
        response = await client.chat(sample_messages)

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "deepseek-v4-pro"
        assert call_kwargs["messages"] == sample_messages
        assert response.choices[0].message.content == mock_openai_response.choices[0].message.content


@pytest.mark.asyncio
async def test_chat_with_retry(
    mock_openai_response: MagicMock,
    sample_messages: list[dict[str, str]],
) -> None:
    """Verify retry on first failure: first call raises APIError, second succeeds."""
    with patch(
        "models.llm_providers.deepseek_client.AsyncOpenAI"
    ) as mock_async_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                APIError(
                    "server_error: 503 Service Unavailable",
                    request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
                    body=None,
                ),
                mock_openai_response,
            ]
        )
        mock_async_openai.return_value = mock_client

        client = DeepSeekClient()
        response = await client.chat(sample_messages)

        assert mock_client.chat.completions.create.call_count == 2
        assert response.choices[0].message.content == mock_openai_response.choices[0].message.content


@pytest.mark.asyncio
async def test_chat_stream(
    mock_openai_stream: list[MagicMock],
    sample_messages: list[dict[str, str]],
) -> None:
    """Verify chat_stream() yields all chunks correctly."""
    with patch(
        "models.llm_providers.deepseek_client.AsyncOpenAI"
    ) as mock_async_openai:
        mock_client = MagicMock()

        async def _stream_iter():
            for chunk in mock_openai_stream:
                yield chunk

        mock_client.chat.completions.create = AsyncMock(return_value=_stream_iter())
        mock_async_openai.return_value = mock_client

        client = DeepSeekClient()
        chunks: list[MagicMock] = []
        async for chunk in client.chat_stream(sample_messages):
            chunks.append(chunk)

        assert len(chunks) == len(mock_openai_stream)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["stream"] is True

        # Verify content tokens collected correctly
        content_parts: list[str] = []
        for chunk in chunks:
            if chunk.choices[0].delta.content:
                content_parts.append(chunk.choices[0].delta.content)
        assert "Hello" in content_parts
        assert "world" in content_parts


@pytest.mark.asyncio
async def test_chat_max_retries_exhausted(
    sample_messages: list[dict[str, str]],
) -> None:
    """Verify that after 3 failures, tenacity raises RetryError."""
    with patch(
        "models.llm_providers.deepseek_client.AsyncOpenAI"
    ) as mock_async_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIError(
                "server_error: 500 Internal Server Error",
                request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
                body=None,
            )
        )
        mock_async_openai.return_value = mock_client

        client = DeepSeekClient()

        with pytest.raises(RetryError):
            await client.chat(sample_messages)

        # Should have been called 3 times (stop_after_attempt(3))
        assert mock_client.chat.completions.create.call_count == 3


def test_init_uses_settings() -> None:
    """Verify that the client reads api_key, base_url, and model from settings."""
    mock_settings = MagicMock()
    mock_settings.deepseek_api_key = "sk-test-deepseek-key"
    mock_settings.deepseek_base_url = "https://api.deepseek.com"
    mock_settings.deepseek_model = "deepseek-v3"

    # DeepSeekClient.__init__ does a local ``from config.settings import settings``,
    # so we must patch the canonical source rather than the re-exported module ref.
    with patch("config.settings.settings", mock_settings):
        client = DeepSeekClient()

        # Lazy init: AsyncOpenAI is NOT created during __init__,
        # but settings are still captured into private attributes.
        assert client._api_key == "sk-test-deepseek-key"
        assert client._base_url == "https://api.deepseek.com"
        assert client._model == "deepseek-v3"
        assert client.model == "deepseek-v3"
