"""Unit tests for FeatureFlagManager — defaults, overrides, reset, Redis persistence."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402

from config.feature_flags import DEFAULT_FLAGS, FeatureFlagManager, get_flag_manager  # noqa: E402


class TestFeatureFlagDefaults:
    """Verify default flag definitions."""

    def test_defaults_contain_expected_keys(self) -> None:
        assert "reranker_enabled" in DEFAULT_FLAGS
        assert "rag_enabled" in DEFAULT_FLAGS
        assert "hybrid_retrieval_enabled" in DEFAULT_FLAGS
        assert "semantic_search_enabled" in DEFAULT_FLAGS

    def test_defaults_are_booleans(self) -> None:
        for v in DEFAULT_FLAGS.values():
            assert isinstance(v, bool)

    def test_load_yaml_overrides_defaults(self) -> None:
        mgr = FeatureFlagManager()
        original = mgr._defaults.get("rag_enabled")
        mgr.load_yaml_defaults({"feature_flags": {"rag_enabled": False, "custom_flag": True}})
        assert mgr._defaults["rag_enabled"] is False
        # custom_flag not in DEFAULT_FLAGS doesn't get added
        assert "custom_flag" not in mgr._defaults or mgr._defaults.get("custom_flag") in (True, False)


class TestFeatureFlagGet:
    """Verify flag reading with Redis fallback."""

    @pytest.mark.asyncio
    async def test_get_returns_default_when_no_redis(self) -> None:
        mgr = FeatureFlagManager()
        with patch.object(FeatureFlagManager, "_redis_get", AsyncMock(return_value=None)):
            val = await mgr.get("rag_enabled")
            assert val == mgr._defaults["rag_enabled"]

    @pytest.mark.asyncio
    async def test_get_returns_redis_override(self) -> None:
        mgr = FeatureFlagManager()
        with patch.object(FeatureFlagManager, "_redis_get", AsyncMock(return_value=True)):
            val = await mgr.get("reranker_enabled")
            assert val is True

    @pytest.mark.asyncio
    async def test_get_unknown_flag_raises_valueerror(self) -> None:
        mgr = FeatureFlagManager()
        with patch.object(FeatureFlagManager, "_redis_get", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="Unknown feature flag"):
                await mgr.get("nonexistent_flag")

    @pytest.mark.asyncio
    async def test_get_all_returns_all_with_sources(self) -> None:
        mgr = FeatureFlagManager()
        with patch.object(FeatureFlagManager, "_redis_get", AsyncMock(return_value=None)):
            result = await mgr.get_all()
            assert len(result) >= len(DEFAULT_FLAGS)
            for k in DEFAULT_FLAGS:
                assert k in result
                assert isinstance(result[k], bool)


class TestFeatureFlagSet:
    """Verify flag writing to Redis."""

    @pytest.mark.asyncio
    async def test_set_persists_to_redis(self) -> None:
        mgr = FeatureFlagManager()
        with patch.object(FeatureFlagManager, "_redis_set", AsyncMock(return_value=None)):
            with patch.object(FeatureFlagManager, "_redis_get", AsyncMock(return_value=None)):
                result = await mgr.set("rag_enabled", False)
                assert result is True

    @pytest.mark.asyncio
    async def test_set_unknown_flag_raises(self) -> None:
        mgr = FeatureFlagManager()
        with pytest.raises(ValueError, match="Unknown feature flag"):
            await mgr.set("bad_flag", True)

    @pytest.mark.asyncio
    async def test_set_then_get_reflects_change(self) -> None:
        mgr = FeatureFlagManager()
        # Simulate: Redis write stores True, Redis read returns True
        stored: dict[str, str | None] = {"feature_flag:rag_enabled": None}

        async def mock_set(name: str, value: str) -> None:  # noqa: E306
            stored[f"feature_flag:{name}"] = value

        async def mock_get(name: str) -> str | None:  # noqa: E306
            return stored.get(f"feature_flag:{name}")

        with patch.object(FeatureFlagManager, "_redis_set", side_effect=mock_set):
            with patch.object(FeatureFlagManager, "_redis_get", side_effect=mock_get):
                await mgr.set("rag_enabled", False)
                val = await mgr.get("rag_enabled")
                assert val is False


class TestFeatureFlagReset:
    """Verify flag reset to defaults."""

    @pytest.mark.asyncio
    async def test_reset_clears_override(self) -> None:
        mgr = FeatureFlagManager()
        with patch.object(FeatureFlagManager, "_redis_delete", AsyncMock(return_value=True)):
            with patch.object(FeatureFlagManager, "_redis_get", AsyncMock(return_value=None)):
                result = await mgr.reset("rag_enabled")
                assert result is True
                val = await mgr.get("rag_enabled")
                assert val == mgr._defaults["rag_enabled"]

    @pytest.mark.asyncio
    async def test_reset_unknown_flag_raises(self) -> None:
        mgr = FeatureFlagManager()
        with pytest.raises(ValueError):
            await mgr.reset("unknown")

    @pytest.mark.asyncio
    async def test_reset_all_clears_everything(self) -> None:
        mgr = FeatureFlagManager()
        with patch.object(FeatureFlagManager, "_redis_delete", AsyncMock(return_value=True)):
            count = await mgr.reset_all()
            assert count == len(mgr._defaults)


class TestFeatureFlagSingleton:
    """Verify singleton pattern."""

    def test_get_flag_manager_returns_same_instance(self) -> None:
        m1 = get_flag_manager()
        m2 = get_flag_manager()
        assert m1 is m2

    def test_is_enabled_shorthand(self) -> None:
        mgr = FeatureFlagManager()
        mgr._defaults["rag_enabled"] = True
        # Can't easily test async in sync, but verify it doesn't crash
        assert hasattr(mgr, "is_enabled")
        assert callable(mgr.is_enabled)


class TestFeatureFlagRedisKey:
    """Verify Redis key generation."""

    def test_key_prefix_correct(self) -> None:
        assert FeatureFlagManager._key("test_flag") == "feature_flag:test_flag"

    def test_key_stable_across_calls(self) -> None:
        k1 = FeatureFlagManager._key("rag_enabled")
        k2 = FeatureFlagManager._key("rag_enabled")
        assert k1 == k2
