"""
Redis Stream-based task queue for asynchronous indexing tasks.

Uses Redis Stream commands (XADD, XREADGROUP, XACK, XGROUP CREATE) to manage
indexing task distribution across multiple worker consumers.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STREAM_KEY = "indexing:tasks"
CONSUMER_GROUP = "indexing_workers"
STATUS_KEY_PREFIX = "indexing:status"


# ---------------------------------------------------------------------------
# IndexingTask dataclass
# ---------------------------------------------------------------------------


@dataclass
class IndexingTask:
    """Represents an asynchronous file-indexing task."""

    task_id: str
    file_path: str
    file_type: str  # "pdf" | "url"
    collection_name: str
    status: str = "pending"  # pending | processing | ready | failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# TaskQueue
# ---------------------------------------------------------------------------


class TaskQueue:
    """Redis Stream-based task queue for IndexingTask messages.

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
    def _task_to_dict(task: IndexingTask) -> dict[str, str]:
        """Serialize an IndexingTask to a flat dict suitable for XADD."""
        data = asdict(task)
        return {k: "" if v is None else str(v) for k, v in data.items()}

    @staticmethod
    def _dict_to_task(data: dict) -> IndexingTask:
        """Deserialize a flat dict (from XREADGROUP) back to an IndexingTask."""
        decoded = {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }
        return IndexingTask(
            task_id=decoded.get("task_id", ""),
            file_path=decoded.get("file_path", ""),
            file_type=decoded.get("file_type", ""),
            collection_name=decoded.get("collection_name", ""),
            status=decoded.get("status", "pending"),
            created_at=decoded.get("created_at", ""),
            error_message=decoded.get("error_message") or None,
        )

    async def _ensure_consumer_group(self) -> None:
        """Create the consumer group if it does not already exist."""
        try:
            await self._redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
        except Exception:  # pragma: no cover – group may already exist
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(self, task: IndexingTask) -> str:
        """Push a task to the Redis Stream.

        Returns the Redis message ID (e.g. ``"1689000000000-0"``).
        """
        await self._ensure_consumer_group()
        fields = self._task_to_dict(task)
        message_id = await self._redis.xadd(STREAM_KEY, fields)
        return message_id.decode() if isinstance(message_id, bytes) else message_id

    async def dequeue(
        self, consumer_name: str, block_ms: int = 5000
    ) -> Optional[tuple[str, IndexingTask]]:
        """Pop a task from the stream (blocking read with timeout).

        Returns ``(message_id, IndexingTask)`` or ``None`` on timeout / error.
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

        for stream_name, messages in results:
            for message_id, fields in messages:
                task = self._dict_to_task(fields)
                mid = message_id.decode() if isinstance(message_id, bytes) else message_id
                return mid, task

        return None

    async def ack(self, message_id: str) -> None:
        """Acknowledge completion of a task message."""
        try:
            await self._redis.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
        except Exception:
            pass

    async def get_status(self, task_id: str) -> Optional[str]:
        """Retrieve the current status of a task from the Redis hash."""
        try:
            raw = await self._redis.hget(f"{STATUS_KEY_PREFIX}:{task_id}", "status")
            if raw:
                return raw.decode() if isinstance(raw, bytes) else raw
            return None
        except Exception:
            return None

    async def update_status(
        self, task_id: str, status: str, error: Optional[str] = None
    ) -> None:
        """Update the task status (and optionally an error message) in Redis."""
        key = f"{STATUS_KEY_PREFIX}:{task_id}"
        mapping: dict[str, str] = {"status": status}
        if error is not None:
            mapping["error_message"] = error
        try:
            await self._redis.hset(key, mapping=mapping)
        except Exception:
            pass

    async def get_pending_count(self) -> int:
        """Return the number of pending messages in the consumer group."""
        try:
            info = await self._redis.xpending(STREAM_KEY, CONSUMER_GROUP)
            # XPENDING without additional args returns a dict with "pending" key
            if isinstance(info, dict):
                return int(info.get("pending", 0))
            return 0
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Module-level convenience functions (singleton pattern)
# ---------------------------------------------------------------------------

_task_queue: Optional[TaskQueue] = None


def _get_queue() -> TaskQueue:
    """Lazily obtain the singleton TaskQueue.

    The singleton requires an async Redis client to have been injected via
    ``init_task_queue`` before use, or a RuntimeError is raised.
    """
    global _task_queue
    if _task_queue is None:
        raise RuntimeError(
            "TaskQueue singleton not initialised – call init_task_queue(redis_client) first"
        )
    return _task_queue


def init_task_queue(redis_client: Redis) -> None:
    """Initialise the module-level TaskQueue singleton.

    Should be called once during application startup with a properly
    configured async Redis client.
    """
    global _task_queue
    _task_queue = TaskQueue(redis_client)


async def enqueue_indexing_task(
    file_path: str, file_type: str, collection_name: str
) -> str:
    """Create an IndexingTask and enqueue it.

    Returns the Redis message ID.
    """
    task = IndexingTask(
        task_id=str(uuid.uuid4()),
        file_path=file_path,
        file_type=file_type,
        collection_name=collection_name,
    )
    queue = _get_queue()
    # Also write initial status hash so check_index_ready can query it.
    await queue.update_status(task.task_id, task.status)
    return await queue.enqueue(task)


async def check_index_ready(task_id: str) -> bool:
    """Return ``True`` if the task status is ``"ready"``."""
    queue = _get_queue()
    status = await queue.get_status(task_id)
    return status == "ready"


async def wait_for_index(task_id: str, timeout: float = 60.0) -> bool:
    """Poll ``get_status`` until the task reaches ``"ready"`` or ``"failed"``.

    Returns ``True`` if the task became ready, ``False`` on failure or timeout.
    """
    queue = _get_queue()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        status = await queue.get_status(task_id)
        if status == "ready":
            return True
        if status == "failed":
            return False
        await asyncio.sleep(0.5)
    return False
