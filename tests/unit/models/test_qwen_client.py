"""Unit tests for QwenClient — async calls, multi-size model routing, and streaming."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from config.settings import settings  # noqa: E402
from models.llm_providers.qwen_client import QwenClient  # noqa: E402


@pytest.mark.asyncio
async def test_chat_success(
    mock_openai_response: MagicMock,
    sample_messages: list[dict[str, str]],
) -> None:
    """Verify chat() returns a valid response on success for the default 'max' model."""
    with patch("models.llm_providers.qwen_client.AsyncOpenAI") as mock_async_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
        mock_async_openai.return_value = mock_client

        client = QwenClient(model_size="max")
        response = await client.chat(sample_messages)

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "qwen-max"
        assert call_kwargs["messages"] == sample_messages
        assert (
            response.choices[0].message.content == mock_openai_response.choices[0].message.content
        )


@pytest.mark.asyncio
async def test_model_size_routing(
    mock_openai_response: MagicMock,
    sample_messages: list[dict[str, str]],
) -> None:
    """Verify that different model_size values in the constructor select the correct model."""
    with patch("models.llm_providers.qwen_client.AsyncOpenAI") as mock_async_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
        mock_async_openai.return_value = mock_client

        # 8b client
        client_8 = QwenClient(model_size="8b")
        await client_8.chat(sample_messages)
        assert (
            mock_client.chat.completions.create.call_args.kwargs["model"]
            == settings.qwen_light_model
        )

        # 32b client
        client_32 = QwenClient(model_size="32b")
        await client_32.chat(sample_messages)
        assert (
            mock_client.chat.completions.create.call_args.kwargs["model"]
            == settings.qwen_medium_model
        )

        # max client
        client_max = QwenClient(model_size="max")
        await client_max.chat(sample_messages)
        assert mock_client.chat.completions.create.call_args.kwargs["model"] == "qwen-max"

        assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_chat_stream(
    mock_openai_stream: list[MagicMock],
    sample_messages: list[dict[str, str]],
) -> None:
    """Verify chat_stream() yields all chunks correctly."""
    with patch("models.llm_providers.qwen_client.AsyncOpenAI") as mock_async_openai:
        mock_client = MagicMock()

        async def _stream_iter():
            for chunk in mock_openai_stream:
                yield chunk

        mock_client.chat.completions.create = AsyncMock(return_value=_stream_iter())
        mock_async_openai.return_value = mock_client

        client = QwenClient(model_size="8b")
        chunks: list[MagicMock] = []
        async for chunk in client.chat_stream(sample_messages):
            chunks.append(chunk)

        assert len(chunks) == len(mock_openai_stream)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == settings.qwen_light_model
        assert call_kwargs["stream"] is True


def test_init_uses_settings() -> None:
    """Verify the client reads configuration from settings (lazy init — no AsyncOpenAI yet)."""
    mock_settings = MagicMock()
    mock_settings.qwen_api_key = "sk-test-qwen-key"
    mock_settings.qwen_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    with patch("models.llm_providers.qwen_client.settings", mock_settings):
        client = QwenClient(model_size="max")

        # Lazy init: AsyncOpenAI is NOT created during __init__,
        # but settings are still captured into private attributes.
        assert client._api_key == "sk-test-qwen-key"
        assert client._base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert client._model == "qwen-max"
        # model property returns the resolved model name from _MODEL_SIZE_MAP
        assert client.model == "qwen-max"


def test_init_default_model_size() -> None:
    """Verify the default model_size is 'max'."""
    with patch("models.llm_providers.qwen_client.AsyncOpenAI") as mock_async_openai:
        mock_client = MagicMock()
        mock_async_openai.return_value = mock_client

        client = QwenClient()
        assert client.model == "qwen-max"
