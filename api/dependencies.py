"""API dependencies — FastAPI Depends injection providers."""

from __future__ import annotations

from typing import Any


async def get_settings() -> Any:
    """Dependency: provide application settings."""
    from config.settings import settings
    return settings
