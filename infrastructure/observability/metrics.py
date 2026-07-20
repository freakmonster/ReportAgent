"""
Prometheus metrics definitions.

Exposes metrics for:
- Workflow / node durations
- LLM API calls & token consumption
- MCP tool calls
- Circuit breaker state
- Active workflows & pending human reviews
- Rate limit hits
"""

from __future__ import annotations

import os
from typing import Optional

try:
    import prometheus_client
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_registry: Optional[CollectorRegistry] = None


def _get_registry() -> CollectorRegistry:
    global _registry  # noqa: PLW0603
    if _registry is None:
        if PROMETHEUS_AVAILABLE:
            _registry = CollectorRegistry(auto_describe=True)
        else:
            _registry = CollectorRegistry()  # type: ignore[assignment]
    return _registry


# ---------------------------------------------------------------------------
# Metric objects
# ---------------------------------------------------------------------------

if PROMETHEUS_AVAILABLE:
    workflow_duration_seconds = Histogram(
        "workflow_duration_seconds",
        "Duration of full workflow execution in seconds.",
        labelnames=["workflow_type", "status"],
        registry=_get_registry(),
    )

    node_duration_seconds = Histogram(
        "node_duration_seconds",
        "Duration per LangGraph node in seconds.",
        labelnames=["node_name", "status"],
        registry=_get_registry(),
    )

    llm_requests_total = Counter(
        "llm_requests_total",
        "Total number of LLM API calls.",
        labelnames=["model", "status"],
        registry=_get_registry(),
    )

    llm_tokens_total = Counter(
        "llm_tokens_total",
        "Total number of tokens consumed.",
        labelnames=["model", "type"],
        registry=_get_registry(),
    )

    mcp_requests_total = Counter(
        "mcp_requests_total",
        "Total number of MCP tool calls.",
        labelnames=["server", "tool", "status"],
        registry=_get_registry(),
    )

    circuit_breaker_state = Gauge(
        "circuit_breaker_state",
        "Current circuit breaker state (0=closed, 1=open, 2=half-open).",
        labelnames=["server"],
        registry=_get_registry(),
    )

    active_workflows = Gauge(
        "active_workflows",
        "Number of currently running workflows.",
        registry=_get_registry(),
    )

    human_review_pending = Gauge(
        "human_review_pending",
        "Number of pending human reviews.",
        registry=_get_registry(),
    )

    rate_limit_hits_total = Counter(
        "rate_limit_hits_total",
        "Total number of rate limit triggers.",
        labelnames=["user_id"],
        registry=_get_registry(),
    )

    dlq_depth = Gauge(
        "dlq_depth",
        "Current dead letter queue depth.",
        registry=_get_registry(),
    )

    index_fallback = Counter(
        "index_fallback",
        "Number of times index search fell back to internal tools.",
        labelnames=["collection_name"],
        registry=_get_registry(),
    )

else:
    # Fallback no-op placeholders when prometheus_client is not installed.
    # They accept the same interface but do nothing.

    class _NoOpMetric:
        """Generic no-op metric that silently discards calls."""

        def labels(self, **kwargs: str) -> "_NoOpMetric":  # type: ignore[no-untyped-def]
            return self

        def observe(self, value: float) -> None:  # noqa: ARG002
            pass

        def inc(self, amount: float = 1) -> None:  # noqa: ARG002
            pass

        def dec(self, amount: float = 1) -> None:  # noqa: ARG002
            pass

        def set(self, value: float) -> None:  # noqa: ARG002
            pass

        def time(self) -> "_NoOpTimer":
            return _NoOpTimer()

    class _NoOpTimer:
        def __enter__(self) -> "_NoOpTimer":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    workflow_duration_seconds = _NoOpMetric()  # type: ignore[assignment]
    node_duration_seconds = _NoOpMetric()  # type: ignore[assignment]
    llm_requests_total = _NoOpMetric()  # type: ignore[assignment]
    llm_tokens_total = _NoOpMetric()  # type: ignore[assignment]
    mcp_requests_total = _NoOpMetric()  # type: ignore[assignment]
    circuit_breaker_state = _NoOpMetric()  # type: ignore[assignment]
    active_workflows = _NoOpMetric()  # type: ignore[assignment]
    human_review_pending = _NoOpMetric()  # type: ignore[assignment]
    rate_limit_hits_total = _NoOpMetric()  # type: ignore[assignment]
    dlq_depth = _NoOpMetric()  # type: ignore[assignment]
    index_fallback = _NoOpMetric()  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_metrics() -> bytes:
    """Return Prometheus text-format metrics (for the ``/metrics`` endpoint).

    Returns an empty byte string when prometheus_client is not installed.
    """
    if not PROMETHEUS_AVAILABLE:
        return b""
    return generate_latest(_get_registry())


def init_metrics(port: int | None = None) -> None:
    """Start a Prometheus HTTP metrics server on a dedicated port.

    Parameters
    ----------
    port:
        Port to bind to. Defaults to ``METRICS_PORT`` env var or ``9090``.

    If prometheus_client is not installed or the port is explicitly set to
    ``0``, this function is a no-op.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if port is None:
        port_str = os.environ.get("METRICS_PORT", "9090")
        try:
            port = int(port_str)
        except ValueError:
            port = 9090

    if port == 0:
        return

    prometheus_client.start_http_server(port, registry=_get_registry())
