"""Locust load-test script for the multi-agent research report API.

Target:   POST /chat/stream  (SSE streaming endpoint)
Run with: locust -f tests/performance/locustfile.py --host=http://localhost:8000

Simulates:
  - deep_report users (peak 100 concurrent)
  - flash_news users
  - SSE event-stream parsing with timeout & error recovery
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from locust import HttpUser, between, events, task

logger = logging.getLogger("locustfile")

# ── Constants ──────────────────────────────────────────────────────────
_ENDPOINT = "/chat/stream"
_SSE_TIMEOUT_S = 60  # max seconds to wait for stream completion
_HEADERS = {"Content-Type": "application/json", "Accept": "text/event-stream"}


# ── Helper: parse SSE stream ───────────────────────────────────────────


def _consume_sse_stream(response: Any, _request_meta: dict[str, Any]) -> tuple[bool, int]:
    """Read an SSE event stream until [DONE] or timeout.

    Returns (success: bool, event_count: int).
    """
    event_count = 0
    start = time.monotonic()

    try:
        for line in response.iter_lines(decode_unicode=True):
            if line is None:
                continue

            # Standard SSE: "data: {...}" or "event: ..." or empty delimiter
            if line.startswith("data: "):
                payload = line[len("data: ") :]
            elif line.startswith("data:"):
                payload = line[len("data:") :].lstrip()
            elif line.startswith("{") or line.startswith("["):
                # Some servers emit raw JSON lines (non-standard but common)
                payload = line
            else:
                # SSE comment / event-type line / empty — skip
                continue

            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning("Unparseable SSE payload: %.100s", payload)
                continue

            event_type = data.get("event", "")
            event_count += 1

            if event_type == "complete":
                logger.info("Stream completed after %d events", event_count)
                return True, event_count

            if event_type == "error":
                logger.warning(
                    "SSE error event: %s", data.get("data", {}).get("message", "unknown")
                )
                return False, event_count

            # Timeout guard
            if time.monotonic() - start > _SSE_TIMEOUT_S:
                logger.warning("SSE stream timed out after %.0fs", time.monotonic() - start)
                return False, event_count

        # Stream ended without "complete" event
        logger.warning("Stream ended prematurely after %d events", event_count)
        return False, event_count

    except Exception as exc:
        logger.error("SSE stream read error: %s", exc)
        return False, event_count


# ── Locust event hooks ─────────────────────────────────────────────────


@events.test_start.add_listener
def on_test_start(environment: Any, **kwargs: Any) -> None:
    """Called once when the test run begins."""
    logger.info(
        "=== Locust load test starting === host=%s users=%d spawn_rate=%d",
        environment.host,
        environment.runner.target_user_count if environment.runner else "N/A",
        environment.runner.spawn_rate if environment.runner else "N/A",
    )


@events.test_stop.add_listener
def on_test_stop(environment: Any, **kwargs: Any) -> None:
    """Called once when the test run ends."""
    if environment.stats is not None:
        logger.info(
            "=== Locust load test finished === total_requests=%d failures=%d avg_ms=%d p95_ms=%d",
            environment.stats.total.num_requests,
            environment.stats.total.num_failures,
            environment.stats.total.avg_response_time,
            environment.stats.total.get_response_time_percentile(0.95),
        )


# ── Base user ──────────────────────────────────────────────────────────


class ReportStreamingUser(HttpUser):
    """Base user for SSE report streaming — shared SSE parsing logic."""

    # 1–5 second wait between tasks (configurable in subclasses)
    wait_time = between(1, 5)

    # Subclasses override these
    _report_type: str = ""

    def on_start(self) -> None:
        """Runs when a simulated user starts."""
        logger.debug("[%s] user started on host=%s", self._report_type, self.host)

    def on_stop(self) -> None:
        """Runs when a simulated user stops."""
        logger.debug("[%s] user stopped", self._report_type)

    @task(1)
    def submit_report_request(self) -> None:
        """POST /chat/stream with SSE response parsing."""
        payload: dict[str, str] = {
            "query": f"测试研报生成 — {self._report_type}",
            "report_type": self._report_type,
            "user_id": "load_test_user",
        }

        # Build a name for the Locust stats entry
        stat_label = f"/chat/stream [{self._report_type}]"

        start_at = time.monotonic()
        event_count = 0

        try:
            with self.client.post(
                _ENDPOINT,
                json=payload,
                headers=_HEADERS,
                stream=True,
                timeout=_SSE_TIMEOUT_S,
                catch_response=True,
                name=stat_label,
            ) as response:
                if response.status_code != 200:
                    response.failure(
                        f"Non-200 status: {response.status_code} "
                        f"body=%.200s" % (response.text[:200] if hasattr(response, "text") else "")
                    )
                    return

                success, event_count = _consume_sse_stream(response, {})

                elapsed = (time.monotonic() - start_at) * 1000

                if success:
                    response.success()
                else:
                    response.failure(
                        f"SSE stream did not complete (events={event_count}) elapsed={elapsed:.0f}ms"
                    )

        except Exception as exc:
            elapsed = (time.monotonic() - start_at) * 1000
            # Locust `catch_response` requires calling failure on the response;
            # when the request itself raises, we record a manual failure event.
            self.environment.events.request.fire(
                request_type="POST",
                name=stat_label,
                response_time=elapsed,
                response_length=0,
                exception=exc,
            )
            logger.error("[%s] request failed: %s", self._report_type, exc)


# ── Concrete user classes ──────────────────────────────────────────────


class DeepReportUser(ReportStreamingUser):
    """Simulates a user requesting a deep_report via SSE streaming."""

    # Slightly longer wait for deep_report (heavier workflow)
    wait_time = between(2, 5)
    _report_type = "deep_report"


class FlashNewsUser(ReportStreamingUser):
    """Simulates a user requesting a flash_news via SSE streaming."""

    wait_time = between(1, 3)
    _report_type = "flash_news"
