"""Edge routing error fallbacks — MCP failure and model fallback."""

from __future__ import annotations


def route_on_mcp_error(state: dict[str, object]) -> str:
    """If MCP call failed, route to internal tool fallback.

    Returns 'internal_search' if MCP error, otherwise 'continue'.
    """
    collection: dict[str, object] = state.get("collection", {})  # type: ignore[assignment]
    error = collection.get("mcp_error", False)  # type: ignore[typeddict-item]
    return "internal_search" if error else "continue"


def route_on_model_error(state: dict[str, object]) -> str:
    """If primary model failed, route to fallback model node.

    Returns 'fallback_model' if error flag set, otherwise 'continue'.
    """
    base: dict[str, object] = state.get("base", {})  # type: ignore[assignment]
    error = base.get("model_fallback", False)  # type: ignore[typeddict-item]
    return "fallback_model" if error else "continue"
