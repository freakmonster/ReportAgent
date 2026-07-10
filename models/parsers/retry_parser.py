"""Retry parser with retry logic for LLM output parsing.

When JSON parsing fails, this component retries with a repair callback
that can fix the text before re-parsing.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from models.parsers.json_parser import JSONParseError, JSONParser

logger = logging.getLogger(__name__)


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, original_text: str = "") -> None:
        super().__init__(message)
        self.original_text = original_text


class RetryParser:
    """Parse LLM JSON output with automatic retry on failure.

    When the initial parse fails, optionally applies a repair callback
    (e.g. fixing the text) and retries.
    """

    def __init__(self, max_retries: int = 3) -> None:
        """Initialize the retry parser.

        Args:
            max_retries: Maximum number of parse attempts (including the first).
        """
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        self._max_retries = max_retries

    def retry_parse(
        self, text: str, repair_callback: Optional[Callable[[str], str]] = None
    ) -> Any:
        """Parse JSON text with retry logic.

        Args:
            text: The raw LLM output to parse.
            repair_callback: Optional sync callable that takes the
                             original/failing text and returns a repaired version.
                             If parsing fails after the initial attempt,
                             this callback is invoked and the result is re-parsed.

        Returns:
            The parsed JSON value.

        Raises:
            RetryExhaustedError: If all retry attempts are exhausted.
        """
        current_text = text

        for attempt in range(1, self._max_retries + 1):
            try:
                return JSONParser.parse(current_text)
            except JSONParseError:
                if attempt >= self._max_retries:
                    logger.warning("retry_parser.exhausted | attempts=%d max=%d", attempt, self._max_retries)
                    raise RetryExhaustedError(
                        f"Failed to parse JSON after {self._max_retries} attempts",
                        original_text=text,
                    )

                if repair_callback is not None:
                    logger.info("retry_parser.retrying | attempt=%d next=%d", attempt, attempt + 1)
                    try:
                        current_text = repair_callback(current_text)
                    except Exception:
                        logger.error("retry_parser.repair_failed | attempt=%d", attempt)
                        # Continue to next attempt even if repair fails
                        continue
                else:
                    # Without a repair callback, retrying the same text won't help
                    raise RetryExhaustedError(
                        f"Failed to parse JSON after {attempt} attempt(s) with no repair callback",
                        original_text=text,
                    )

        # Should not reach here, but safety net
        raise RetryExhaustedError(
            "Failed to parse JSON after all retries",
            original_text=text,
        )
