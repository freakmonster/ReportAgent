"""Unit tests for auth middleware."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from api.middlewares.auth import auth_dependency  # noqa: E402


class TestAuthDependency:
    """Verify authentication logic."""

    @pytest.mark.asyncio
    async def test_no_auth_returns_anonymous_in_dev(self) -> None:
        with patch("config.settings.settings.environment", "dev"):
            request = MagicMock()
            request.headers = {}
            result = await auth_dependency(request)
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_api_key_auth(self) -> None:
        request = MagicMock()
        request.headers = {"X-API-Key": "test-key-12345"}
        result = await auth_dependency(request)
        assert result == "key:test-key"

    @pytest.mark.asyncio
    async def test_bearer_token_invalid_raises(self) -> None:
        request = MagicMock()
        request.headers = {"Authorization": "Bearer invalid.token.here"}
        with pytest.raises(HTTPException) as exc_info:
            await auth_dependency(request)
        assert exc_info.value.status_code == 401
