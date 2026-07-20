"""
Model router with V2.1 dual-level circuit breaker.
- User-level: 429 rate limit errors only affect that specific user
- Service-level: global circuit breaker trips at 50% error rate (1-min sliding window)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    LIGHT = "light"  # qwen3-8b
    MEDIUM = "medium"  # qwen3-32b
    HEAVY = "heavy"  # deepseek-v3 (primary) -> qwen-max (fallback)


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit broken, all requests go to fallback
    HALF_OPEN = "half_open"  # Probing if service recovered


class ModelRouter:
    """V2.1 dual-level circuit breaker router.

    User-level: 429 errors route that specific user to fallback.
    Service-level: 50% error rate in 1-min sliding window opens global circuit.
    """

    def __init__(self) -> None:
        from config.settings import settings

        # Lazy-initialized provider clients (created on first use to avoid
        # crashing on import when API keys are not set — e.g. during tests).
        self._deepseek: object | None = None
        self._qwen_light: object | None = None
        self._qwen_medium: object | None = None
        self._qwen_max: object | None = None

        # Circuit breaker state
        self._circuit_state: CircuitState = CircuitState.CLOSED
        self._circuit_opened_at: float = 0.0
        self._circuit_timeout: float = float(settings.cb_timeout)  # default 30s
        self._failure_threshold: int = settings.cb_failure_threshold  # default 3

        # Sliding window: list of (timestamp, success) tuples
        self._window: list[tuple[float, bool]] = []
        self._window_duration: float = 60.0  # 1 minute

        # User-level fallback markers (429 errors)
        self._user_fallback: set[str] = set()

    def _get_deepseek(self) -> object:
        if self._deepseek is None:
            from models.llm_providers.deepseek_client import DeepSeekClient

            self._deepseek = DeepSeekClient()
        return self._deepseek

    def _get_qwen_light(self) -> object:
        if self._qwen_light is None:
            from models.llm_providers.qwen_client import QwenClient

            self._qwen_light = QwenClient(model_size="8b")
        return self._qwen_light

    def _get_qwen_medium(self) -> object:
        if self._qwen_medium is None:
            from models.llm_providers.qwen_client import QwenClient

            self._qwen_medium = QwenClient(model_size="32b")
        return self._qwen_medium

    def _get_qwen_max(self) -> object:
        if self._qwen_max is None:
            from models.llm_providers.qwen_client import QwenClient

            self._qwen_max = QwenClient(model_size="max")
        return self._qwen_max

    async def route(self, tier: ModelTier, user_id: str | None = None) -> tuple[str, object]:
        """Route to appropriate model based on tier and circuit state.

        Args:
            tier: The model tier to route to (LIGHT, MEDIUM, or HEAVY).
            user_id: Optional user identifier for user-level fallback tracking.

        Returns:
            A tuple of (model_display_name, client_instance).

        Raises:
            ValueError: If an unknown tier is provided.
        """
        if tier == ModelTier.LIGHT:
            return ("qwen3-8b", self._get_qwen_light())

        if tier == ModelTier.MEDIUM:
            return ("qwen3-32b", self._get_qwen_medium())

        if tier == ModelTier.HEAVY:
            # Check user-level fallback first
            if user_id is not None and user_id in self._user_fallback:
                logger.warning("User %s in fallback mode (429), routing to qwen-max", user_id)
                return ("qwen-max (user fallback)", self._get_qwen_max())

            # Check global circuit breaker
            state = self._get_circuit_state()
            if state == CircuitState.OPEN:
                logger.warning("Circuit OPEN, routing to qwen-max")
                return ("qwen-max (circuit open)", self._get_qwen_max())

            if state == CircuitState.HALF_OPEN:
                logger.info("Circuit HALF_OPEN, probing deepseek-v3")

            return ("deepseek-v3", self._get_deepseek())

        raise ValueError(f"Unknown tier: {tier}")

    async def record_result(
        self,
        model_name: str,
        success: bool,
        status_code: int | None = None,
        user_id: str | None = None,
    ) -> None:
        """Record API call result for circuit breaker tracking.

        Args:
            model_name: Display name of the model that was called.
            success: Whether the call succeeded.
            status_code: HTTP status code from the API response, if available.
            user_id: Optional user identifier for 429 rate-limit tracking.
        """
        now = time.time()

        # User-level 429 handling
        if status_code == 429 and user_id is not None:
            self._user_fallback.add(user_id)
            logger.warning("User %s rate limited (429), added to fallback", user_id)
            return

        # Only track deepseek results for global circuit breaker
        if "deepseek" not in model_name.lower():
            return

        # Clean old entries from sliding window
        self._window = [(ts, ok) for ts, ok in self._window if now - ts <= self._window_duration]

        # Record this result
        self._window.append((now, success))

        # Calculate error rate
        total = len(self._window)
        errors = sum(1 for _, ok in self._window if not ok)

        if total > 0 and errors / total >= 0.5 and self._circuit_state == CircuitState.CLOSED:
            self._circuit_state = CircuitState.OPEN
            self._circuit_opened_at = now
            logger.error(
                "Circuit OPEN: %d/%d errors (%.1f%%)",
                errors,
                total,
                errors / total * 100,
            )

    def _get_circuit_state(self) -> CircuitState:
        """Get current circuit state, handling timeout transitions."""
        if self._circuit_state == CircuitState.OPEN:
            elapsed = time.time() - self._circuit_opened_at
            if elapsed >= self._circuit_timeout:
                self._circuit_state = CircuitState.HALF_OPEN
                logger.info("Circuit transitioned to HALF_OPEN after %.1fs", elapsed)
                return CircuitState.HALF_OPEN
        return self._circuit_state

    def get_circuit_state(self) -> CircuitState:
        """Public accessor for the current circuit breaker state."""
        return self._get_circuit_state()

    def clear_user_fallback(self, user_id: str) -> None:
        """Remove a user from the 429 fallback set.

        Args:
            user_id: The user identifier to clear.
        """
        self._user_fallback.discard(user_id)


# Module-level singleton
router = ModelRouter()
