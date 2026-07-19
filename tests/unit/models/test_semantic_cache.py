"""Unit tests for semantic cache (LLM response caching).

Tests cover:
- Prompt hashing determinism
- Cache get/set cycle (with mock Redis)
- Cache miss (disabled, Redis unavailable)
- TTL configuration
- Cache invalidation
- Cache flush
- CachedLLMCall context manager
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from models.semantic_cache import (
    CachedLLMCall,
    _hash_prompt,
    cache_flush,
    cache_get,
    cache_invalidate,
    cache_set,
)


# ── Prompt hashing ─────────────────────────────────────────────────────

class TestPromptHashing:
    """Verify prompt hash is deterministic and sensitive to parameters."""

    def test_same_input_produces_same_hash(self) -> None:
        msgs = [{"role": "user", "content": "test"}]
        h1 = _hash_prompt(msgs, 0.7, 2048)
        h2 = _hash_prompt(msgs, 0.7, 2048)
        assert h1 == h2

    def test_different_content_produces_different_hash(self) -> None:
        msgs1 = [{"role": "user", "content": "test A"}]
        msgs2 = [{"role": "user", "content": "test B"}]
        assert _hash_prompt(msgs1, 0.7, 2048) != _hash_prompt(msgs2, 0.7, 2048)

    def test_different_temperature_produces_different_hash(self) -> None:
        msgs = [{"role": "user", "content": "test"}]
        assert _hash_prompt(msgs, 0.7, 2048) != _hash_prompt(msgs, 0.1, 2048)

    def test_different_max_tokens_produces_different_hash(self) -> None:
        msgs = [{"role": "user", "content": "test"}]
        assert _hash_prompt(msgs, 0.7, 2048) != _hash_prompt(msgs, 0.7, 512)

    def test_hash_is_64_char_hex(self) -> None:
        msgs = [{"role": "user", "content": "test"}]
        h = _hash_prompt(msgs, 0.7, 2048)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_order_independent(self) -> None:
        """Different dict key orderings produce the same hash (sort_keys=True)."""
        msgs1 = [{"content": "test", "role": "user"}]
        msgs2 = [{"role": "user", "content": "test"}]
        assert _hash_prompt(msgs1, 0.7, 2048) == _hash_prompt(msgs2, 0.7, 2048)


# ── Cache get/set cycle ────────────────────────────────────────────────

class TestCacheGetSet:
    """Verify cache read/write with mock Redis."""

    @pytest.mark.asyncio
    async def test_cache_miss_when_disabled(self) -> None:
        with patch("models.semantic_cache._is_cache_enabled", return_value=False):
            result = await cache_get([{"role": "user", "content": "test"}])
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_miss_when_redis_unavailable(self) -> None:
        with patch("models.semantic_cache._is_cache_enabled", return_value=True):
            with patch("models.semantic_cache._get_redis", AsyncMock(return_value=None)):
                result = await cache_get([{"role": "user", "content": "test"}])
                assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_stored_value(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        stored = {"choices": [{"message": {"content": "world"}}]}

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(stored))

        with patch("models.semantic_cache._is_cache_enabled", return_value=True):
            with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
                result = await cache_get(msgs)
                assert result == stored

    @pytest.mark.asyncio
    async def test_cache_set_stores_with_ttl(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        # Use spec to prevent MagicMock auto-creating model_dump/dict attrs,
        # forcing cache_set to use the choices-based serialisation fallback.
        mock_choice = MagicMock()
        mock_choice.message.content = "world"
        mock_response = MagicMock(spec=["choices"])
        mock_response.choices = [mock_choice]

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=None)

        with patch("models.semantic_cache._is_cache_enabled", return_value=True):
            with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
                with patch("models.semantic_cache._ttl_seconds", return_value=3600):
                    await cache_set(msgs, mock_response)

        mock_redis.set.assert_called_once()
        args = mock_redis.set.call_args
        assert args.kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_cache_set_noop_when_disabled(self) -> None:
        mock_redis = MagicMock()
        with patch("models.semantic_cache._is_cache_enabled", return_value=False):
            with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
                await cache_set([], None)
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_on_error(self) -> None:
        msgs = [{"role": "user", "content": "test"}]
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("Redis down"))

        with patch("models.semantic_cache._is_cache_enabled", return_value=True):
            with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
                result = await cache_get(msgs)
                assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_survives_error(self) -> None:
        msgs = [{"role": "user", "content": "test"}]
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "resp"

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(side_effect=RuntimeError("Redis full"))

        with patch("models.semantic_cache._is_cache_enabled", return_value=True):
            with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
                await cache_set(msgs, mock_response)  # Should not raise


# ── Cache invalidation ─────────────────────────────────────────────────

class TestCacheInvalidation:
    """Verify cache entry deletion."""

    @pytest.mark.asyncio
    async def test_invalidate_deletes_key(self) -> None:
        msgs = [{"role": "user", "content": "delete-me"}]
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(return_value=1)

        with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
            result = await cache_invalidate(msgs)
            assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_returns_false_when_not_found(self) -> None:
        msgs = [{"role": "user", "content": "not-exists"}]
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(return_value=0)

        with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
            result = await cache_invalidate(msgs)
            assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_graceful_when_redis_unavailable(self) -> None:
        with patch("models.semantic_cache._get_redis", AsyncMock(return_value=None)):
            result = await cache_invalidate([{"role": "user", "content": "x"}])
            assert result is False


# ── Cache flush ────────────────────────────────────────────────────────

class TestCacheFlush:
    """Verify bulk cache deletion."""

    @pytest.mark.asyncio
    async def test_flush_deletes_all_matching_keys(self) -> None:
        mock_redis = MagicMock()
        mock_redis.scan = AsyncMock(return_value=(0, ["llm:cache:abc", "llm:cache:def"]))
        mock_redis.delete = AsyncMock(return_value=2)

        with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
            count = await cache_flush()
            assert count == 2
            mock_redis.delete.assert_called_once_with("llm:cache:abc", "llm:cache:def")

    @pytest.mark.asyncio
    async def test_flush_returns_zero_when_no_keys(self) -> None:
        mock_redis = MagicMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))

        with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
            count = await cache_flush()
            assert count == 0

    @pytest.mark.asyncio
    async def test_flush_handles_pagination(self) -> None:
        """SCAN may return cursor != 0 for large key sets."""
        mock_redis = MagicMock()
        call_count = [0]

        async def mock_scan(cursor, match=None, count=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return (1, ["llm:cache:a"])
            return (0, ["llm:cache:b"])

        mock_redis.scan = mock_scan
        mock_redis.delete = AsyncMock(return_value=2)

        with patch("models.semantic_cache._get_redis", AsyncMock(return_value=mock_redis)):
            count = await cache_flush()
            assert count == 2

    @pytest.mark.asyncio
    async def test_flush_graceful_when_redis_unavailable(self) -> None:
        with patch("models.semantic_cache._get_redis", AsyncMock(return_value=None)):
            count = await cache_flush()
            assert count == 0


# ── CachedLLMCall context manager ──────────────────────────────────────

class TestCachedLLMCall:
    """Verify the async context manager wrapper."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        cached = {"choices": [{"message": {"content": "hello"}}]}

        with patch("models.semantic_cache.cache_get", AsyncMock(return_value=cached)):
            async with CachedLLMCall(msgs) as result:
                assert result == cached
                assert result is not None

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]

        with patch("models.semantic_cache.cache_get", AsyncMock(return_value=None)):
            async with CachedLLMCall(msgs) as result:
                assert result is None

    @pytest.mark.asyncio
    async def test_hit_property(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]

        with patch("models.semantic_cache.cache_get", AsyncMock(return_value={"x": 1})):
            wrapper = CachedLLMCall(msgs)
            async with wrapper as result:
                assert result is not None
            assert wrapper.hit is True

        with patch("models.semantic_cache.cache_get", AsyncMock(return_value=None)):
            wrapper = CachedLLMCall(msgs)
            async with wrapper as result:
                assert result is None
            assert wrapper.hit is False
