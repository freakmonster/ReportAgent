"""
Redis Stream-based Dead Letter Queue for failed async index building tasks.

Captures failures from the index builder (``retrieval/pipelines/build_index.py``)
into a persistent Redis Stream so they can be inspected, retried, or escalated
instead of being silently dropped.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STREAM_KEY = "dlq:index_build"
CONSUMER_GROUP = "dlq_consumers"


# ---------------------------------------------------------------------------
# DLQMessage dataclass
# ---------------------------------------------------------------------------


@dataclass
class DLQMessage:
    """Represents a failed index-building task pushed to the Dead Letter Queue."""

    collection_name: str
    """Which index collection failed."""
    error_traceback: str
    """Full exception traceback."""
    payload: dict
    """The original indexing task payload."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    """ISO-format timestamp of the failure."""


# ---------------------------------------------------------------------------
# DeadLetterQueue
# ---------------------------------------------------------------------------


class DeadLetterQueue:
    """Redis Stream-based Dead Letter Queue for failed index-building tasks.

    Parameters
    ----------
    redis_client:
        An async Redis client (``redis.asyncio.Redis``) from
        ``infrastructure.cache.redis_client``.
    """

    def __init__(self, redis_client: Redis) -> None:
        self._redis: Redis = redis_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _message_to_dict(message: DLQMessage) -> dict[str, str]:
        """Serialize a DLQMessage to a flat dict suitable for XADD."""
        data = asdict(message)
        # payload is a nested dict – JSON-encode it for the flat stream format
        data["payload"] = json.dumps(data["payload"], ensure_ascii=False)
        return {k: "" if v is None else str(v) for k, v in data.items()}

    @staticmethod
    def _dict_to_message(data: dict) -> DLQMessage:
        """Deserialize a flat dict (from XREADGROUP / XRANGE) back to a DLQMessage."""
        decoded = {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }
        return DLQMessage(
            collection_name=decoded.get("collection_name", ""),
            error_traceback=decoded.get("error_traceback", ""),
            payload=json.loads(decoded.get("payload", "{}")),
            timestamp=decoded.get("timestamp", ""),
        )

    async def _ensure_consumer_group(self) -> None:
        """Create the consumer group if it does not already exist."""
        try:
            await self._redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def push(self, collection_name: str, error_traceback: str, payload: dict) -> str:
        """Push a DLQMessage to the Redis Stream via XADD.

        Returns the Redis message ID (e.g. ``"1689000000000-0"``).
        """
        await self._ensure_consumer_group()
        message = DLQMessage(
            collection_name=collection_name,
            error_traceback=error_traceback,
            payload=payload,
        )
        fields = self._message_to_dict(message)
        try:
            message_id = await self._redis.xadd(STREAM_KEY, fields)
        except Exception:
            return ""
        mid = message_id.decode() if isinstance(message_id, bytes) else message_id

        # Best-effort update of Prometheus metric
        try:
            from infrastructure.observability.metrics import dlq_depth

            dlq_depth.set(await self.get_depth())
        except ImportError:
            pass

        return mid

    async def consume(
        self, consumer_name: str, block_ms: int = 5000
    ) -> Optional[tuple[str, DLQMessage]]:
        """Read a message from the stream via XREADGROUP (blocking).

        Returns ``(message_id, DLQMessage)`` or ``None`` on timeout / error.
        """
        await self._ensure_consumer_group()
        try:
            streams = {STREAM_KEY: ">"}
            results = await self._redis.xreadgroup(
                CONSUMER_GROUP,
                consumer_name,
                streams,
                count=1,
                block=block_ms,
            )
        except Exception:
            return None

        if not results:
            return None

        for _stream_name, messages in results:
            for message_id, fields in messages:
                msg = self._dict_to_message(fields)
                mid = message_id.decode() if isinstance(message_id, bytes) else message_id
                return mid, msg

        return None

    async def ack(self, message_id: str) -> None:
        """XACK the message after a successful retry."""
        try:
            await self._redis.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
        except Exception:
            pass

    async def get_depth(self) -> int:
        """Return the current number of messages in the stream via XLEN."""
        try:
            length = await self._redis.xlen(STREAM_KEY)
            return int(length)
        except Exception:
            return 0

    async def list_failed(self, count: int = 10) -> list[DLQMessage]:
        """List recent failed messages via XREVRANGE without consuming them."""
        try:
            results = await self._redis.xrevrange(STREAM_KEY, count=count)
        except Exception:
            return []

        messages: list[DLQMessage] = []
        for message_id, fields in results:
            messages.append(self._dict_to_message(fields))

        return messages


# ---------------------------------------------------------------------------
# Module-level convenience functions (singleton pattern)
# ---------------------------------------------------------------------------

_dlq: Optional[DeadLetterQueue] = None


def _get_dlq() -> DeadLetterQueue:
    """Lazily obtain the singleton DeadLetterQueue.

    The singleton requires an async Redis client to have been injected via
    ``init_dead_letter_queue`` before use, or a RuntimeError is raised.
    """
    global _dlq
    if _dlq is None:
        raise RuntimeError(
            "DeadLetterQueue singleton not initialised – "
            "call init_dead_letter_queue(redis_client) first"
        )
    return _dlq


def init_dead_letter_queue(redis_client: Redis) -> None:
    """Initialise the module-level DeadLetterQueue singleton.

    Should be called once during application startup with a properly
    configured async Redis client.
    """
    global _dlq
    _dlq = DeadLetterQueue(redis_client)


async def push_to_dlq(collection_name: str, error_traceback: str, payload: dict) -> str:
    """Push a failure to the Dead Letter Queue.

    Returns the Redis message ID.
    """
    dlq = _get_dlq()
    return await dlq.push(collection_name, error_traceback, payload)


async def get_dlq_depth() -> int:
    """Return the current number of messages in the Dead Letter Queue."""
    dlq = _get_dlq()
    return await dlq.get_depth()
