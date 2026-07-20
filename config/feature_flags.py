"""Feature Flag Manager — runtime toggle system with Redis persistence.

AGENTS.md §6.1/§6.2 compliant: YAML defaults → Redis hot-switch → runtime read.

Architecture:
- Default values loaded from config/environments/*.yaml (``feature_flags`` block)
- Runtime overrides stored in Redis (key: ``feature_flag:{name}``) for cross-process consistency
- Admin API (``/admin/flags``) enables hot-switching without restart
- Falls back to YAML defaults when Redis is unavailable
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Redis key prefix for feature flag overrides
_FLAG_KEY_PREFIX = "feature_flag:"

# Default flag definitions — overridden by YAML config on init
DEFAULT_FLAGS: dict[str, bool] = {
    "reranker_enabled": False,
    "rag_enabled": True,
    "llm_cache_enabled": False,
    "hybrid_retrieval_enabled": True,
    "semantic_search_enabled": True,
    "bm25_enabled": True,
    "circuit_breaker_enabled": True,
    "auto_rerank_enabled": False,
}


class FeatureFlagManager:
    """Manages feature flags with Redis-backed runtime overrides.

    Thread-safe via asyncio.Lock for in-process reads, Redis provides
    cross-process consistency.
    """

    def __init__(self) -> None:
        self._defaults: dict[str, bool] = dict(DEFAULT_FLAGS)
        self._lock = asyncio.Lock()

    # ── Initialisation ───────────────────────────────────────────────

    def load_yaml_defaults(self, yaml_data: dict[str, Any]) -> None:
        """Merge YAML feature_flags block into defaults.

        Called once at startup from settings initialisation.
        """
        flags_from_yaml = yaml_data.get("feature_flags", {})
        if flags_from_yaml:
            self._defaults.update(flags_from_yaml)
            logger.debug("feature_flags.yaml_loaded", count=len(flags_from_yaml))

    # ── Read ─────────────────────────────────────────────────────────

    async def get(self, name: str) -> bool:
        """Get the current effective value of a feature flag.

        Priority: Redis override > YAML default.

        Raises:
            ValueError: If the flag name is not recognised.
        """
        if name not in self._defaults:
            raise ValueError(f"Unknown feature flag: '{name}'")

        async with self._lock:
            redis_val = await self._redis_get(name)
            if redis_val is not None:
                return redis_val
            return self._defaults[name]

    async def get_all(self) -> dict[str, bool]:
        """Return all flags with their effective values."""
        async with self._lock:
            result: dict[str, bool] = {}
            for name in self._defaults:
                redis_val = await self._redis_get(name)
                result[name] = redis_val if redis_val is not None else self._defaults[name]
            return result

    async def is_enabled(self, name: str) -> bool:
        """Shorthand for ``await get(name)``."""
        return await self.get(name)

    # ── Write (via Admin API) ────────────────────────────────────────

    async def set(self, name: str, value: bool) -> bool:
        """Set a feature flag override in Redis.

        Args:
            name: Flag name (must exist in defaults).
            value: True to enable, False to disable.

        Returns:
            True if the flag was set successfully.

        Raises:
            ValueError: If the flag name is not recognised.
        """
        if name not in self._defaults:
            raise ValueError(f"Unknown feature flag: '{name}'")

        async with self._lock:
            await self._redis_set(name, value)
            logger.info(f"feature_flag.updated name={name} value={value}")
            return True

    async def reset(self, name: str) -> bool:
        """Remove a Redis override, reverting to the YAML default."""
        if name not in self._defaults:
            raise ValueError(f"Unknown feature flag: '{name}'")

        async with self._lock:
            await self._redis_delete(name)
            logger.info(f"feature_flag.reset name={name}")
            return True

    async def reset_all(self) -> int:
        """Remove all Redis overrides, reverting to YAML defaults.

        Returns:
            Number of keys deleted.
        """
        count = 0
        async with self._lock:
            for name in self._defaults:
                deleted = await self._redis_delete(name)
                if deleted:
                    count += 1
        logger.info(f"feature_flag.all_reset count={count}")
        return count

    # ── Redis helpers ────────────────────────────────────────────────

    @staticmethod
    def _key(name: str) -> str:
        return f"{_FLAG_KEY_PREFIX}{name}"

    @staticmethod
    async def _redis_get(name: str) -> bool | None:
        try:
            from infrastructure.cache.redis_client import get_redis

            redis = get_redis()
            val = await redis.get(FeatureFlagManager._key(name))
            if val is None:
                return None
            return val.lower() in ("true", "1", "yes")
        except Exception:
            return None

    @staticmethod
    async def _redis_set(name: str, value: bool) -> None:
        try:
            from infrastructure.cache.redis_client import get_redis

            redis = get_redis()
            await redis.set(
                FeatureFlagManager._key(name),
                "true" if value else "false",
            )
        except Exception as exc:
            logger.warning(f"feature_flag.redis_write_failed name={name} error={exc}")

    @staticmethod
    async def _redis_delete(name: str) -> bool:
        try:
            from infrastructure.cache.redis_client import get_redis

            redis = get_redis()
            deleted = await redis.delete(FeatureFlagManager._key(name))
            return deleted > 0
        except Exception:
            return False


# ── Module-level singleton ────────────────────────────────────────────────

_flag_manager: FeatureFlagManager | None = None


def get_flag_manager() -> FeatureFlagManager:
    """Return the singleton FeatureFlagManager."""
    global _flag_manager
    if _flag_manager is None:
        _flag_manager = FeatureFlagManager()
    return _flag_manager


def init_feature_flags(yaml_data: dict[str, Any]) -> FeatureFlagManager:
    """Initialise the feature flag manager from YAML config.

    Called once in settings initialisation.
    """
    mgr = get_flag_manager()
    mgr.load_yaml_defaults(yaml_data)
    return mgr
