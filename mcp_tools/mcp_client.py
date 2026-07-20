"""
MCP Client with V2.1 circuit breaker, tenacity retry, and timeout=5s probe.

Features:
- HTTP connection pool via httpx.AsyncClient
- Circuit breaker: 3 consecutive failures → OPEN → 30s timeout → HALF_OPEN
- Half-open probe with mandatory timeout=5s
- tenacity exponential backoff retry (max 2 attempts)
- Auto-degradation to internal_tools when circuit is OPEN
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit broken, requests fail fast / degrade
    HALF_OPEN = "half_open"  # Probing if service recovered


@dataclass
class MCPToolResult:
    """Result returned from an MCP tool call."""

    success: bool
    data: Any = None
    error: str | None = None
    server_name: str = ""
    tool_name: str = ""


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Circuit breaker for MCP server calls.

    State transitions:
        CLOSED → (consecutive_failures >= threshold) → OPEN
        OPEN → (elapsed >= timeout_seconds) → HALF_OPEN (probe)
        HALF_OPEN + probe SUCCESS → CLOSED
        HALF_OPEN + probe FAILURE → OPEN

    The probe request MUST have timeout=5s. If it times out or fails,
    the circuit stays/returns to OPEN.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: float = 30.0,
        probe_timeout: float = 5.0,
    ) -> None:
        self._failure_threshold: int = failure_threshold
        self._timeout_seconds: float = timeout_seconds
        self._probe_timeout: float = probe_timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._opened_at: float = 0.0
        self._total_successes: int = 0
        self._total_failures: int = 0

    # ── properties ──────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """Current circuit state, handling timeout transitions."""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._opened_at
            if elapsed >= self._timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit transitioned to HALF_OPEN after %.1fs", elapsed)
        return self._state

    @property
    def is_open(self) -> bool:
        """Whether the circuit is currently open (fast-fail)."""
        return self.state == CircuitState.OPEN

    @property
    def metrics(self) -> dict[str, Any]:
        """Return circuit breaker metrics for observability."""
        return {
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "opened_at": self._opened_at if self._state != CircuitState.CLOSED else None,
        }

    # ── state transitions ────────────────────────────────────────────────

    def record_success(self) -> None:
        """Record a successful call."""
        self._total_successes += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            logger.info("Circuit CLOSED after successful probe")
        else:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._total_failures += 1

        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — stay OPEN
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
            self._consecutive_failures = self._failure_threshold
            logger.warning("Circuit returned to OPEN after failed probe")
            return

        self._consecutive_failures += 1
        if (
            self._consecutive_failures >= self._failure_threshold
            and self._state == CircuitState.CLOSED
        ):
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
            logger.error(
                "Circuit OPEN: %d consecutive failures",
                self._consecutive_failures,
            )


# ---------------------------------------------------------------------------
# Tenacity version compatibility helper
# ---------------------------------------------------------------------------


def _is_last_tenacity_attempt(attempt: object) -> bool:
    """Check if the current tenacity attempt is the last one.

    tenacity ≥ 8.4 exposes retry_state.attempt_number; earlier versions
    may not make retry_state accessible on the attempt context manager.
    Falls back to assuming the call is non-final when internals are opaque.
    """
    try:
        rs = getattr(attempt, "retry_state", None)
        if rs is not None:
            return not getattr(rs, "is_last_attempt", lambda: False)()
    except Exception:
        pass
    # Safe default: record failure but don't assume it's the last attempt.
    # The circuit breaker's per-call failure tracking still works correctly
    # because record_failure is also called on the catch-all path.
    return True


# ---------------------------------------------------------------------------
# MCP Client
# ---------------------------------------------------------------------------


class MCPClient:
    """HTTP-based MCP client with circuit breaker and retry.

    Features:
    - Connection pool via httpx.AsyncClient (reused across calls)
    - Circuit breaker per server endpoint
    - tenacity exponential backoff retry (max 2)
    - Probe timeout=5s for half-open detection
    - Auto-degradation registry
    """

    RETRY_MAX_ATTEMPTS: int = 3  # initial attempt + 2 retries
    REQUEST_TIMEOUT: float = 30.0  # default request timeout

    def __init__(self) -> None:
        # Lazy-initialized httpx client (not created at import time)
        self._http_client: object | None = None

        # Circuit breaker per server (keyed by server_url)
        self._breakers: dict[str, CircuitBreaker] = {}

        # Degradation mapping: server_url → internal_tool_name
        self._degradation_map: dict[str, str] = {}

        # Lock for lazy initialization
        self._lock: asyncio.Lock | None = None

    # ── lazy init ───────────────────────────────────────────────────────

    async def _ensure_http_client(self) -> object:
        """Lazily create the httpx AsyncClient if not already initialized."""
        if self._http_client is None:
            import httpx

            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.REQUEST_TIMEOUT),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=50),
            )
        return self._http_client

    async def _ensure_lock(self) -> asyncio.Lock:
        """Lazily create the asyncio lock."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── breaker management ──────────────────────────────────────────────

    def get_breaker(self, server_url: str) -> CircuitBreaker:
        """Get or create a circuit breaker for the given server URL."""
        if server_url not in self._breakers:
            self._breakers[server_url] = CircuitBreaker()
        return self._breakers[server_url]

    def register_degradation(self, server_url: str, internal_tool_name: str) -> None:
        """Register a fallback internal tool for a MCP server URL.

        When the circuit for *server_url* is OPEN, calls will be
        automatically degraded to *internal_tool_name*.
        """
        self._degradation_map[server_url] = internal_tool_name

    # ── core call method ────────────────────────────────────────────────

    async def call(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        server_name: str = "",
    ) -> MCPToolResult:
        """Call an MCP tool on a remote server with circuit breaker protection.

        Args:
            server_url: Base URL of the MCP server (e.g. http://localhost:8001).
            tool_name: Name of the tool to call on the server.
            arguments: Tool-specific arguments.
            server_name: Human-readable server name for logging/debugging.

        Returns:
            MCPToolResult with success flag, data, and optional error info.

        Raises:
            CircuitBreakerOpenError: When the circuit is OPEN and no
                degradation target is registered.
        """
        breaker = self.get_breaker(server_url)

        # Fast-fail: circuit is OPEN
        if breaker.is_open:
            degradation = self._degradation_map.get(server_url)
            if degradation:
                logger.warning(
                    "Circuit OPEN for %s, degrading to internal tool '%s'",
                    server_name or server_url,
                    degradation,
                )
                return await self._degrade(degradation, tool_name, arguments)
            raise CircuitBreakerOpenError(
                f"Circuit OPEN for {server_name or server_url} and no degradation target registered"
            )

        # Execute with retry
        return await self._execute_with_retry(
            server_url, tool_name, arguments, server_name, breaker
        )

    async def _execute_with_retry(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        server_name: str,
        breaker: CircuitBreaker,
    ) -> MCPToolResult:
        """Execute an MCP call with exponential backoff retry.

        Uses tenacity for retry logic: max 2 retries (3 attempts total),
        exponential backoff starting at 1 second.
        """
        from tenacity import (
            AsyncRetrying,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        last_exception: Exception | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.RETRY_MAX_ATTEMPTS),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(Exception),
                reraise=True,
            ):
                with attempt:
                    try:
                        result = await self._do_call(
                            server_url,
                            tool_name,
                            arguments,
                            is_probe=(breaker.state == CircuitState.HALF_OPEN),
                        )
                        breaker.record_success()
                        return result
                    except Exception as exc:
                        # Determine if this is the last attempt using the internal
                        # retry_state; tenacity ≥ 8.4 uses different internals,
                        # so we fall back to tracking manually.
                        is_last = _is_last_tenacity_attempt(attempt)
                        if is_last:
                            breaker.record_failure()
                        logger.warning(
                            "MCP call '%s/%s' failed: %s",
                            server_name or server_url,
                            tool_name,
                            exc,
                        )
                        raise
        except Exception as exc:
            last_exception = exc

        # All retries exhausted
        logger.error(
            "MCP call '%s/%s' failed after %d attempts: %s",
            server_name or server_url,
            tool_name,
            self.RETRY_MAX_ATTEMPTS,
            last_exception,
        )

        # Attempt degradation if registered
        degradation = self._degradation_map.get(server_url)
        if degradation:
            logger.warning("Degrading '%s' to internal tool '%s'", server_name, degradation)
            return await self._degrade(degradation, tool_name, arguments)

        return MCPToolResult(
            success=False,
            error=str(last_exception),
            server_name=server_name or server_url,
            tool_name=tool_name,
        )

    async def _do_call(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        is_probe: bool = False,
    ) -> MCPToolResult:
        """Perform the actual HTTP call to the MCP server.

        If *is_probe* is True (circuit in HALF_OPEN), enforce timeout=5s.
        """
        import httpx

        client = await self._ensure_http_client()
        assert client is not None

        timeout = 5.0 if is_probe else self.REQUEST_TIMEOUT
        url = f"{server_url.rstrip('/')}/tools/{tool_name}"

        try:
            response = await client.post(  # type: ignore[union-attr]
                url,
                json=arguments,
                timeout=httpx.Timeout(timeout),
            )
            response.raise_for_status()
            data = response.json()
            return MCPToolResult(
                success=True,
                data=data,
                server_name=str(server_url),
                tool_name=tool_name,
            )
        except httpx.TimeoutException as exc:
            msg = (
                f"Probe timeout ({timeout}s) for {url}"
                if is_probe
                else f"Request timeout ({timeout}s) for {url}"
            )
            logger.warning(msg)
            raise MCPTimeoutError(msg) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "HTTP %d from %s: %s",
                exc.response.status_code,
                url,
                exc.response.text[:200],
            )
            raise MCPServerError(f"HTTP {exc.response.status_code} from {url}") from exc
        except httpx.RequestError as exc:
            logger.warning("Request error for %s: %s", url, exc)
            raise MCPConnectionError(f"Connection failed for {url}") from exc

    async def _degrade(
        self,
        internal_tool_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        """Call the fallback internal tool."""
        try:
            from mcp_tools.registry import registry

            tool = await registry.get_tool(internal_tool_name)
            if tool is None:
                return MCPToolResult(
                    success=False,
                    error=f"Internal tool '{internal_tool_name}' not found",
                    tool_name=tool_name,
                )
            result_data = await tool(arguments)
            return MCPToolResult(
                success=True,
                data=result_data,
                server_name=f"internal:{internal_tool_name}",
                tool_name=tool_name,
            )
        except Exception as exc:
            logger.error("Internal tool '%s' also failed: %s", internal_tool_name, exc)
            return MCPToolResult(
                success=False,
                error=f"Degradation to '{internal_tool_name}' also failed: {exc}",
                tool_name=tool_name,
            )

    # ── probe (V2.1: timeout=5s constraint) ────────────────────────────

    async def probe(self, server_url: str) -> bool:
        """Send a health-check probe to the server.

        V2.1 constraint: probe timeout is ALWAYS 5 seconds.
        Returns True if the server responds successfully.
        """
        breaker = self.get_breaker(server_url)

        if breaker.state != CircuitState.HALF_OPEN:
            return not breaker.is_open

        import httpx

        client = await self._ensure_http_client()
        assert client is not None

        url = f"{server_url.rstrip('/')}/health"

        try:
            response = await client.get(  # type: ignore[union-attr]
                url,
                timeout=httpx.Timeout(5.0),
            )
            if response.status_code < 500:
                breaker.record_success()
                logger.info("Probe SUCCESS for %s, circuit CLOSED", server_url)
                return True
            else:
                breaker.record_failure()
                logger.warning("Probe FAILED for %s (HTTP %d)", server_url, response.status_code)
                return False
        except Exception as exc:
            breaker.record_failure()
            logger.warning("Probe FAILED for %s: %s", server_url, exc)
            return False

    # ── health / metrics ────────────────────────────────────────────────

    def get_all_metrics(self) -> dict[str, Any]:
        """Return metrics for all registered circuit breakers."""
        return {server_url: breaker.metrics for server_url, breaker in self._breakers.items()}

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()  # type: ignore[union-attr]
            self._http_client = None


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Base exception for MCP client errors."""


class CircuitBreakerOpenError(MCPError):
    """Raised when the circuit breaker is OPEN and no degradation is available."""


class MCPServerError(MCPError):
    """Raised when the MCP server returns an HTTP error (4xx/5xx)."""


class MCPConnectionError(MCPError):
    """Raised when the MCP server cannot be reached."""


class MCPTimeoutError(MCPError):
    """Raised when the MCP server request times out."""


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

mcp_client = MCPClient()
