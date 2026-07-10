"""
OpenTelemetry distributed tracing setup.

Features:
- TracerProvider with BatchSpanProcessor
- OTLPSpanExporter (configurable endpoint, default localhost:4317)
- ConsoleSpanExporter fallback for development
- Async context manager ``trace_span`` for manual instrumentation
- Graceful no-op when OpenTelemetry is not installed

The ``tracer`` is initialised at module-load time as a lazy proxy. Calling
``init_tracer()`` sets the actual provider, after which the proxy produces
real spans.  The ``tracer`` reference itself never changes, so ``from …
import tracer`` is safe.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any, AsyncIterator, Dict, Optional

# ---------------------------------------------------------------------------
# No-op tracer stand-ins (defined *first* so they are available regardless of
# whether OpenTelemetry is installed)
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """Minimal span stand-in."""

    def set_attributes(self, attributes: Dict[str, Any]) -> None:  # noqa: ARG002
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    """Minimal tracer stand-in."""

    def start_as_current_span(self, name: str) -> _NoOpSpan:  # noqa: ARG002
        return _NoOpSpan()


# ---------------------------------------------------------------------------
# Try importing OpenTelemetry; if unavailable, use no-op stand-ins.
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OTEL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_otel_export_endpoint() -> str:
    """Read OTLP endpoint from env or return default."""
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")


def _get_service_name() -> str:
    """Read service name from env or return default."""
    return os.environ.get("OTEL_SERVICE_NAME", "research_agent")


# ---------------------------------------------------------------------------
# Module-level tracer (lazy proxy — always valid, never rebinds)
# ---------------------------------------------------------------------------
_tracer_provider: Any = None

if OTEL_AVAILABLE:
    # trace.get_tracer() returns a proxy that delegates to whatever provider is
    # set at call time.  The proxy is valid immediately; it simply produces
    # no-op spans until a real provider is configured via ``init_tracer()``.
    tracer: Any = trace.get_tracer(_get_service_name())
else:
    tracer = _NoOpTracer()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def init_tracer() -> None:
    """Initialise the OpenTelemetry tracer provider.

    - If ``OTEL_ENABLED`` is explicitly set to ``"false"`` (case-insensitive),
      tracing is disabled (no-op).
    - Uses OTLPSpanExporter by default; falls back to ConsoleSpanExporter when
      ``OTEL_USE_CONSOLE_EXPORTER="true"`` or when the OTLP endpoint is
      unreachable.
    - When OpenTelemetry is not installed, this is a no-op (``tracer`` stays
      as a no-op stand-in).
    """
    global _tracer_provider  # noqa: PLW0603

    if os.environ.get("OTEL_ENABLED", "").strip().lower() == "false":
        return

    if not OTEL_AVAILABLE:
        return

    resource = Resource(attributes={SERVICE_NAME: _get_service_name()})

    # Decide which exporter to use
    use_console = os.environ.get("OTEL_USE_CONSOLE_EXPORTER", "").strip().lower() == "true"

    if use_console:
        exporter = ConsoleSpanExporter()
    else:
        endpoint = _get_otel_export_endpoint()
        try:
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        except Exception:  # noqa: BLE001
            # Fall back to console exporter on misconfiguration
            exporter = ConsoleSpanExporter()

    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    _tracer_provider = provider


def shutdown_tracer() -> None:
    """Gracefully shut down the tracer provider, flushing pending spans.

    Safe to call even when tracing was never initialised.
    """
    if not OTEL_AVAILABLE:
        return
    if _tracer_provider is not None:
        _tracer_provider.shutdown()


# ---------------------------------------------------------------------------
# Convenience: async context manager for manual spans
# ---------------------------------------------------------------------------


def _resolve_tracer() -> Any:
    """Return the current tracer, preferring the module-level proxy."""
    if tracer is not None:
        return tracer
    if OTEL_AVAILABLE:
        return trace.get_tracer(_get_service_name())
    return _NoOpTracer()


@contextlib.asynccontextmanager
async def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Any]:
    """Async context manager that creates and yields an OpenTelemetry span.

    Usage::

        async with trace_span("my_operation", {"key": "val"}) as span:
            ...

    When OpenTelemetry is unavailable, yields a no-op span.
    """
    _t = _resolve_tracer()
    with _t.start_as_current_span(name) as span:
        if attributes:
            span.set_attributes(attributes)
        yield span
