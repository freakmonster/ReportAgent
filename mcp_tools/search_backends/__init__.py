"""Search backends package — strategy pattern for pluggable search.

Provide ``get_search_backend()`` factory that returns the configured backend.

Configuration: ``search_backend`` in config/environments/*.yaml
  - ``"tavily"`` → TavilySearchBackend (requires TAVILY_API_KEY)
  - ``"mock"`` → MockSearchBackend (zero-config, deterministic)
"""

from __future__ import annotations

from functools import lru_cache


def get_search_backend() -> object:
    """Factory: return the configured search backend singleton.

    Uses ``lru_cache`` to ensure a single instance is reused.
    Backend selection is controlled by ``settings.search_backend``.

    Returns:
        BaseSearchBackend instance.

    Raises:
        ValueError: If the configured backend is unknown.
    """
    return _cached_get_backend()


@lru_cache(maxsize=1)
def _cached_get_backend() -> object:
    """Cached factory — called at most once per process lifetime."""
    from config.settings import settings

    backend_name = getattr(settings, "search_backend", "tavily")

    if backend_name == "tavily":
        from .tavily_backend import TavilySearchBackend
        return TavilySearchBackend()

    if backend_name == "mock":
        from .mock_backend import MockSearchBackend
        return MockSearchBackend()

    raise ValueError(
        f"Unknown search_backend '{backend_name}'. "
        f"Valid options: 'tavily', 'mock'."
    )
