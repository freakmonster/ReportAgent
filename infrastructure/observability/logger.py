"""
Structured JSON logging using structlog.

Features:
- JSON-formatted output to stdout
- Standard fields: timestamp, level, logger_name, module, function, line_number
- trace_id injection via contextvars
- Log level configurable via Settings.LOG_LEVEL
"""

from __future__ import annotations

import contextvars
import logging
import sys
from typing import Any

try:
    import structlog
    from structlog.typing import EventDict, WrappedLogger

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

# ---------------------------------------------------------------------------
# trace_id context variable (set by middleware later)
# ---------------------------------------------------------------------------
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


def set_trace_id(trace_id: str) -> None:
    """Set the trace_id for the current async context."""
    _trace_id_var.set(trace_id)


def get_trace_id() -> str | None:
    """Get the current trace_id from the async context."""
    return _trace_id_var.get()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _resolve_log_level() -> str:
    """Read LOG_LEVEL from Settings if available, otherwise default to 'INFO'."""
    try:
        from config.settings import Settings  # type: ignore[import-untyped]

        return getattr(Settings, "LOG_LEVEL", "INFO").upper()
    except ImportError:
        return "INFO"


def _add_processor_fields(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Inject standard fields into every log event."""
    import logging

    record: logging.LogRecord | None = event_dict.get("_record")
    if record is None:
        # Fallback: derive caller info from _frame if available
        frame = event_dict.get("_frame")
        if frame is not None:
            event_dict["module"] = frame.f_code.co_name
            event_dict["function"] = frame.f_code.co_name
        else:
            event_dict["module"] = "unknown"
            event_dict["function"] = "unknown"
        event_dict["line_number"] = 0
    else:
        event_dict["module"] = record.module
        event_dict["function"] = record.funcName
        event_dict["line_number"] = record.lineno

    event_dict["logger_name"] = record.name if record else "root"
    event_dict["level"] = record.levelname.lower() if record else method_name

    # Inject trace_id
    tid = get_trace_id()
    if tid is not None:
        event_dict["trace_id"] = tid

    return event_dict


# ---------------------------------------------------------------------------
# configured logger instance
# ---------------------------------------------------------------------------

def _build_logger() -> Any:
    """Build and return a configured structlog logger.

    Returns a stdlib logging.Logger as a fallback when structlog is not installed.
    """
    if not STRUCTLOG_AVAILABLE:
        fallback = logging.getLogger("research_agent")
        fallback.setLevel(_resolve_log_level())
        if not fallback.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                    '"logger_name": "%(name)s", "module": "%(module)s", '
                    '"function": "%(funcName)s", "line_number": %(lineno)d, '
                    '"event": "%(message)s"}',
                    datefmt="%Y-%m-%dT%H:%M:%SZ",
                )
            )
            fallback.addHandler(handler)
        return fallback

    log_level_str = _resolve_log_level()
    log_level = getattr(logging, log_level_str, logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _add_processor_fields,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set the root logger level
    logging.getLogger().setLevel(log_level)

    return structlog.get_logger("research_agent")


logger = _build_logger()
