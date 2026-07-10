"""
Observability package: structured logging, distributed tracing, and Prometheus metrics.
"""

from infrastructure.observability.logger import (
    get_trace_id,
    logger,
    set_trace_id,
)
from infrastructure.observability.metrics import (
    active_workflows,
    circuit_breaker_state,
    dlq_depth,
    get_metrics,
    human_review_pending,
    index_fallback,
    init_metrics,
    llm_requests_total,
    llm_tokens_total,
    mcp_requests_total,
    node_duration_seconds,
    rate_limit_hits_total,
    workflow_duration_seconds,
)
from infrastructure.observability.tracer import (
    init_tracer,
    shutdown_tracer,
    trace_span,
    tracer,
)

__all__ = [
    # logger
    "logger",
    "set_trace_id",
    "get_trace_id",
    # tracer
    "tracer",
    "trace_span",
    "init_tracer",
    "shutdown_tracer",
    # metrics
    "workflow_duration_seconds",
    "node_duration_seconds",
    "llm_requests_total",
    "llm_tokens_total",
    "mcp_requests_total",
    "circuit_breaker_state",
    "active_workflows",
    "human_review_pending",
    "rate_limit_hits_total",
    "dlq_depth",
    "index_fallback",
    "get_metrics",
    "init_metrics",
]
