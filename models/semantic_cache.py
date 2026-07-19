"""Semantic Cache for LLM responses.

Caches LLM API responses keyed by prompt hash (SHA256), using Redis as the
storage backend.  Designed as a strategy-pattern compliant optional layer per
AGENTS.md §6.1/§6.2.

Features:
- SHA256 prompt hashing (deterministic, collision-resistant) — includes model name
- Configurable TTL (default 1 hour)
- YAML toggle ``llm_cache_enabled`` (config/environments/*.yaml)
- Graceful fallback: cache miss → LLM call → cache write
- Non-blocking on Redis unavailable (logs warning, continues without cache)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Default TTL: 1 hour (3600 seconds)
_DEFAULT_TTL = 3600

# Cache key prefix to namespace keys
_CACHE_KEY_PREFIX = "llm:cache:"


def _hash_prompt(
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    model: str = "",
) -> str:
    """Generate a deterministic cache key from prompt parameters.

    Uses SHA256 over a canonical JSON representation of:
    - messages (role + content)
    - temperature
    - max_tokens
    - model (to prevent cross-model cache collisions)

    Args:
        messages: Chat messages list (role, content).
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.
        model: Model identifier string (e.g., "deepseek-v4-pro").

    Returns:
        64-char hex SHA256 digest.
    """
    canonical = json.dumps(
        {
            "messages": [
                {"role": m.get("role", ""), "content": m.get("content", "")}
                for m in messages
            ],
            "temperature": round(temperature, 4),
            "max_tokens": max_tokens,
            "model": model,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_key(prompt_hash: str) -> str:
    """Build Redis key from prompt hash."""
    return f"{_CACHE_KEY_PREFIX}{prompt_hash}"


def _is_cache_enabled() -> bool:
    """Check if semantic cache is enabled via config."""
    try:
        from config.settings import settings
        return bool(getattr(settings, "llm_cache_enabled", False))
    except Exception:
        return False


def _ttl_seconds() -> int:
    """Read cache TTL from settings or default."""
    try:
        from config.settings import settings
        return int(getattr(settings, "llm_cache_ttl", _DEFAULT_TTL))
    except Exception:
        return _DEFAULT_TTL


async def _get_redis() -> Any | None:
    """Get Redis client (non-blocking, returns None if unavailable)."""
    try:
        from infrastructure.cache.redis_client import get_redis
        return get_redis()
    except Exception:
        return None


async def cache_get(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str = "",
) -> Optional[dict[str, Any]]:
    """Attempt to retrieve a cached LLM response.

    Args:
        messages: Chat messages list.
        temperature: Sampling temperature used for the call.
        max_tokens: Max tokens parameter used for the call.
        model: Model identifier string for cross-model cache isolation.

    Returns:
        Cached response dict (matching OpenAI response format), or None on miss.
    """
    if not _is_cache_enabled():
        return None

    try:
        redis = await _get_redis()
        if redis is None:
            return None

        prompt_hash = _hash_prompt(messages, temperature, max_tokens, model)
        key = _cache_key(prompt_hash)
        cached = await redis.get(key)

        if cached is None:
            return None

        parsed = json.loads(cached)
        logger.debug(f"semantic_cache.hit key={key[:30]}")
        return parsed
    except Exception as exc:
        logger.warning(f"semantic_cache.get_failed: {exc}")
        return None


async def cache_set(
    messages: list[dict[str, str]],
    response: Any,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str = "",
) -> None:
    """Store an LLM response in the semantic cache.

    Args:
        messages: Chat messages list (for key generation).
        response: The raw API response to cache (must be JSON-serialisable).
        temperature: Sampling temperature used.
        max_tokens: Max tokens parameter used.
        model: Model identifier string for cross-model cache isolation.

    Raises:
        Nothing — all errors are caught and logged.
    """
    if not _is_cache_enabled():
        return

    try:
        redis = await _get_redis()
        if redis is None:
            return

        prompt_hash = _hash_prompt(messages, temperature, max_tokens, model)
        key = _cache_key(prompt_hash)
        ttl = _ttl_seconds()

        # Serialise response to JSON
        if hasattr(response, "model_dump"):
            serialised = response.model_dump()
        elif hasattr(response, "dict"):
            serialised = response.dict()
        elif isinstance(response, dict):
            serialised = response
        else:
            try:
                serialised = {
                    "choices": [
                        {"message": {"content": choice.message.content}}
                        for choice in response.choices
                    ]
                }
            except Exception:
                logger.debug(f"semantic_cache.cannot_serialise type={type(response).__name__}")
                return

        await redis.set(key, json.dumps(serialised, ensure_ascii=False), ex=ttl)
        logger.debug(f"semantic_cache.stored key={key[:30]} ttl={ttl}")
    except Exception as exc:
        logger.debug(f"semantic_cache.set_failed: {exc}")


async def cache_invalidate(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str = "",
) -> bool:
    """Remove a specific cached entry.

    Args:
        messages: Same messages used for the original call.
        temperature: Same temperature parameter.
        max_tokens: Same max_tokens parameter.
        model: Model identifier string.

    Returns:
        True if an entry was deleted, False otherwise.
    """
    try:
        redis = await _get_redis()
        if redis is None:
            return False

        prompt_hash = _hash_prompt(messages, temperature, max_tokens, model)
        key = _cache_key(prompt_hash)
        deleted = await redis.delete(key)
        return deleted > 0
    except Exception as exc:
        logger.debug(f"semantic_cache.invalidate_failed: {exc}")
        return False


async def cache_flush() -> int:
    """Remove ALL semantic cache entries.

    Returns:
        Number of keys deleted.
    """
    try:
        redis = await _get_redis()
        if redis is None:
            return 0

        pattern = f"{_CACHE_KEY_PREFIX}*"
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = await redis.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break

        if not keys:
            return 0

        return await redis.delete(*keys)
    except Exception as exc:
        logger.debug(f"semantic_cache.flush_failed: {exc}")
        return 0


# ── Convenience: async context manager for cached LLM calls ──────────────

class CachedLLMCall:
    """Async context manager that wraps an LLM call with semantic caching.

    Usage::

        async with CachedLLMCall(messages, temp=0.7, max_tokens=2048, model="deepseek-v3") as result:
            if result is not None:
                return result  # Cache hit (dict)
            # Cache miss: make LLM call
            response = await client.chat(messages, ...)
            await cache_set(messages, response, temp=0.7, max_tokens=2048, model="deepseek-v3")
            return response
    """

    def __init__(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: str = "",
    ) -> None:
        self.messages = messages
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model
        self.hit: bool = False
        self.cached_result: Optional[dict[str, Any]] = None

    async def __aenter__(self) -> Optional[dict[str, Any]]:
        self.cached_result = await cache_get(
            self.messages, self.temperature, self.max_tokens, self.model
        )
        self.hit = self.cached_result is not None
        if self.hit:
            return self.cached_result
        return None  # Cache miss → caller makes LLM call

    async def __aexit__(self, *args: Any) -> None:
        pass  # cache_set() is called explicitly by the caller after LLM call
