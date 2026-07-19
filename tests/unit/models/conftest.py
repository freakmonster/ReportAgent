"""Shared pytest fixtures for model-layer unit tests.

IMPORTANT: This file is loaded by pytest before test collection.
It must NOT import from the project under test — only set up sys.path and fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Ensure project root is on sys.path BEFORE any project imports ──
_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_openai_response() -> MagicMock:
    """Mock a successful OpenAI API chat completion response."""
    response = MagicMock()
    choice = MagicMock()
    message = MagicMock()
    message.role = "assistant"
    message.content = "{\"answer\": \"This is a mocked response from the LLM.\"}"
    choice.message = message
    choice.index = 0
    choice.finish_reason = "stop"
    response.choices = [choice]
    response.id = "chatcmpl-mock-001"
    response.model = "mock-model"
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.total_tokens = 150
    # chat() calls response.model_dump() — return self so assertions work
    response.model_dump.return_value = response
    return response


@pytest.fixture
def mock_openai_stream() -> list[MagicMock]:
    """Mock a streaming OpenAI response — returns a list of chunk mocks."""
    chunks: list[MagicMock] = []
    tokens = ["Hello", ", ", "world", "!", None]  # None = finish_reason set

    for i, token in enumerate(tokens):
        chunk = MagicMock()
        choice = MagicMock()
        delta = MagicMock()

        if token is not None:
            delta.content = token
            choice.delta = delta
            choice.finish_reason = None
        else:
            delta.content = None
            choice.delta = delta
            choice.finish_reason = "stop"

        choice.index = 0
        chunk.choices = [choice]
        chunk.id = f"chatcmpl-stream-mock-{i}"
        chunk.model = "mock-model"
        # chat_stream() yields chunk.model_dump() — return self so assertions work
        chunk.model_dump.return_value = chunk
        chunks.append(chunk)

    return chunks


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock application settings for LLM client tests."""
    settings = MagicMock()
    settings.deepseek_api_key = "sk-test-deepseek-key"
    settings.deepseek_base_url = "https://api.deepseek.com"
    settings.deepseek_model = "deepseek-v3"
    settings.qwen_api_key = "sk-test-qwen-key"
    settings.qwen_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    settings.qwen_model = "qwen-max"
    settings.qwen_light_model = "qwen3-8b"
    settings.qwen_medium_model = "qwen3-32b"
    settings.cb_failure_threshold = 3
    settings.cb_timeout = 30
    return settings


@pytest.fixture
def sample_messages() -> list[dict[str, str]]:
    """Sample chat messages for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, who are you?"},
    ]
