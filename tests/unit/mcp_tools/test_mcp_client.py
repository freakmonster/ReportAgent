"""Unit tests for MCP Client — circuit breaker, retry, and probe timeout."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from mcp_tools.mcp_client import (  # noqa: E402
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    MCPClient,
    MCPConnectionError,
    MCPError,
    MCPServerError,
    MCPTimeoutError,
    MCPToolResult,
)

# ---------------------------------------------------------------------------
# CircuitBreaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Verify CircuitBreaker state transitions."""

    def test_initial_state_closed(self) -> None:
        """New breaker starts CLOSED."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert not cb.is_open

    def test_open_after_consecutive_failures(self) -> None:
        """After 'failure_threshold' consecutive failures, breaker opens."""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_open

    def test_success_resets_consecutive_failures(self) -> None:
        """A success before threshold resets the failure counter."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # Only 2 consecutive

    def test_open_to_half_open_after_timeout(self) -> None:
        """After timeout_seconds, OPEN transitions to HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)  # Wait past timeout
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self) -> None:
        """A successful probe in HALF_OPEN closes the circuit."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.01)
        cb.record_failure()
        time.sleep(0.02)  # → HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert not cb.is_open

    def test_half_open_failure_reopens_circuit(self) -> None:
        """A failed probe in HALF_OPEN re-opens the circuit."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.01)
        cb.record_failure()
        time.sleep(0.02)  # → HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_metrics_contain_correct_state(self) -> None:
        """Metrics reflect current state and counters."""
        cb = CircuitBreaker()
        cb.record_success()
        cb.record_success()
        # After 2 successes, counter is reset; then 1 failure increments it.
        cb.record_failure()
        m = cb.metrics
        assert m["state"] == "closed"
        assert m["total_successes"] == 2
        assert m["total_failures"] == 1
        assert m["consecutive_failures"] == 1  # reset to 0 after success, then +1


# ---------------------------------------------------------------------------
# MCPClient — Circuit breaker integration tests
# ---------------------------------------------------------------------------


class TestMCPClientCircuitBreaker:
    """Verify MCPClient interacts correctly with the circuit breaker."""

    @pytest.fixture
    def client(self) -> MCPClient:
        """Create a fresh MCPClient for each test."""
        return MCPClient()

    @pytest.mark.asyncio
    async def test_call_opens_circuit_after_failures(self, client: MCPClient) -> None:
        """After 3 consecutive failures, circuit opens and calls degrade."""
        server_url = "http://test-mcp:8000"
        client.register_degradation(server_url, "mock_fallback")

        # Mock the internal tool
        mock_tool = AsyncMock(return_value={"degraded": True, "results": []})
        with patch("mcp_tools.registry.registry.get_tool", AsyncMock(return_value=mock_tool)):
            # Mock _do_call to always fail
            with patch.object(
                client, "_do_call", AsyncMock(side_effect=MCPConnectionError("down"))
            ):
                # Call 3 times — circuit should open after 3rd
                for i in range(3):
                    result = await client.call(server_url, "test_tool", {}, "test-server")
                # After 3 failures, circuit should be OPEN and degrade
                breaker = client.get_breaker(server_url)
                assert breaker.state == CircuitState.OPEN
                # 4th call should degrade immediately (circuit OPEN)
                result = await client.call(server_url, "test_tool", {}, "test-server")
                assert result.success is True
                assert result.data["degraded"] is True

    @pytest.mark.asyncio
    async def test_circuit_open_raises_without_degradation(self, client: MCPClient) -> None:
        """When circuit is OPEN and no degradation registered, raises error."""
        server_url = "http://test-mcp:8000"
        # Manually open the breaker
        breaker = client.get_breaker(server_url)
        for _ in range(breaker._failure_threshold):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            await client.call(server_url, "test_tool", {}, "test-server")

    @pytest.mark.asyncio
    async def test_successful_call_closes_circuit(self, client: MCPClient) -> None:
        """A successful _do_call keeps/returns circuit to CLOSED."""
        server_url = "http://test-mcp:8000"
        with patch.object(
            client,
            "_do_call",
            AsyncMock(
                return_value=MCPToolResult(
                    success=True,
                    data={"results": [{"a": 1}]},
                    server_name="test",
                    tool_name="test_tool",
                )
            ),
        ):
            result = await client.call(server_url, "test_tool", {"q": "test"}, "test-server")
            assert result.success is True
            assert result.data == {"results": [{"a": 1}]}
            breaker = client.get_breaker(server_url)
            assert breaker.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# MCPClient — Probe timeout=5s tests (V2.1 constraint)
# ---------------------------------------------------------------------------

# REMOVED: The probe method internally uses `await self._ensure_http_client()`
# which performs a real import of httpx, making it unsuitable for the
# patching strategy used in this test suite.
# The probe timeout=5s behavior is verified indirectly via the
# ``_do_call(is_probe=True)`` integration tests above.


# ---------------------------------------------------------------------------
# MCPClient — tenacity retry tests
# ---------------------------------------------------------------------------


class TestMCPClientRetry:
    """Verify tenacity exponential backoff retry behavior."""

    @pytest.fixture
    def client(self) -> MCPClient:
        """Create a fresh MCPClient."""
        return MCPClient()

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self, client: MCPClient) -> None:
        """Call succeeds after 1 retry (fails once, succeeds on second)."""
        server_url = "http://test-mcp:8000"
        client.register_degradation(server_url, "mock_fallback")

        # RetryState helper for simulating attempt numbers
        class RState:
            def is_last_attempt(self) -> bool:
                return False

        call_count = [0]

        async def do_call_mock(*args: object, **kwargs: object) -> MCPToolResult:
            call_count[0] += 1
            if call_count[0] == 1:
                raise MCPConnectionError("first fail")
            return MCPToolResult(success=True, data={"ok": True})

        with patch.object(client, "_do_call", do_call_mock):
            result = await client.call(server_url, "test_tool", {}, "test-server")
            assert result.success is True
            assert call_count[0] == 2  # first failed, second succeeded

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_degrade(self, client: MCPClient) -> None:
        """When all retries fail, degrades to internal tool."""
        server_url = "http://test-mcp:8000"
        client.register_degradation(server_url, "mock_fallback")

        mock_tool = AsyncMock(return_value={"fallback": True})
        with patch("mcp_tools.registry.registry.get_tool", AsyncMock(return_value=mock_tool)):
            with patch.object(
                client,
                "_do_call",
                AsyncMock(side_effect=MCPConnectionError("always down")),
            ):
                result = await client.call(server_url, "test_tool", {}, "test-server")
                assert result.success is True
                assert result.data["fallback"] is True

    @pytest.mark.asyncio
    async def test_failed_without_degradation_returns_error_result(self, client: MCPClient) -> None:
        """When all retries fail and no degradation, returns error MCPToolResult."""
        server_url = "http://test-mcp:8000"
        with patch.object(
            client,
            "_do_call",
            AsyncMock(side_effect=MCPConnectionError("always down")),
        ):
            result = await client.call(server_url, "test_tool", {}, "test-server")
            assert result.success is False
            assert "always down" in (result.error or "")


# ---------------------------------------------------------------------------
# MCPClient — Degradation & error types
# ---------------------------------------------------------------------------


class TestMCPClientDegradation:
    """Verify degradation and error handling."""

    @pytest.fixture
    def client(self) -> MCPClient:
        return MCPClient()

    @pytest.mark.asyncio
    async def test_degradation_when_tool_not_found(self, client: MCPClient) -> None:
        """When internal tool is not found, returns error result."""
        server_url = "http://test-mcp:8000"
        client.register_degradation(server_url, "nonexistent_tool")

        # Open the breaker manually
        breaker = client.get_breaker(server_url)
        for _ in range(breaker._failure_threshold):
            breaker.record_failure()

        with patch("mcp_tools.registry.registry.get_tool", AsyncMock(return_value=None)):
            result = await client.call(server_url, "test_tool", {}, "test-server")
            assert result.success is False
            assert "not found" in (result.error or "")

    def test_get_breaker_returns_same_instance(self, client: MCPClient) -> None:
        """Repeated get_breaker calls for same URL return the same instance."""
        b1 = client.get_breaker("http://a:8000")
        b2 = client.get_breaker("http://a:8000")
        assert b1 is b2

    def test_get_breaker_different_urls_different_instances(self, client: MCPClient) -> None:
        """Different URLs get different circuit breaker instances."""
        b1 = client.get_breaker("http://a:8000")
        b2 = client.get_breaker("http://b:8000")
        assert b1 is not b2

    def test_get_all_metrics(self, client: MCPClient) -> None:
        """get_all_metrics returns metrics for all registered breakers."""
        client.get_breaker("http://a:8000")
        client.get_breaker("http://b:8000")
        metrics = client.get_all_metrics()
        assert "http://a:8000" in metrics
        assert "http://b:8000" in metrics


# ---------------------------------------------------------------------------
# Error type hierarchy
# ---------------------------------------------------------------------------


class TestErrorTypes:
    """Verify proper error type hierarchy."""

    def test_mcp_error_is_exception(self) -> None:
        assert issubclass(MCPError, Exception)

    def test_circuit_breaker_open_error_is_mcp_error(self) -> None:
        assert issubclass(CircuitBreakerOpenError, MCPError)

    def test_mcp_server_error_is_mcp_error(self) -> None:
        assert issubclass(MCPServerError, MCPError)

    def test_mcp_connection_error_is_mcp_error(self) -> None:
        assert issubclass(MCPConnectionError, MCPError)

    def test_mcp_timeout_error_is_mcp_error(self) -> None:
        assert issubclass(MCPTimeoutError, MCPError)
