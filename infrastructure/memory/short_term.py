"""Short-term memory management backed by Redis ZSET.

Key format: memory:short:{user_id}:{session_id}
Each entry is stored as a JSON member with a Unix-timestamp score.
ZSET ordered from oldest (rank 0) to newest (rank -1).
"""

import json
import time
import logging

from infrastructure.cache.redis_client import get_redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MEMORY_KEY_FMT: str = "memory:short:{user_id}:{session_id}"
_MAX_ENTRIES: int = 20
_TTL_SECONDS: int = 48 * 3600  # 48 hours


def _build_key(user_id: str, session_id: str) -> str:
    """Build the Redis key for a user-session pair."""
    return _MEMORY_KEY_FMT.format(user_id=user_id, session_id=session_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def save_memory(user_id: str, session_id: str, entry: dict) -> None:
    """Write a memory entry into the session ZSET.

    - Only the latest 20 entries are retained (older entries trimmed).
    - The key expires after 48 hours.
    """
    redis = get_redis()
    key = _build_key(user_id, session_id)

    score = time.time()
    member = json.dumps(entry, ensure_ascii=False)

    await redis.zadd(key, {member: score})
    # Keep the latest 20 entries – ranks are 0-based, so -21 removes beyond the last 20
    await redis.zremrangebyrank(key, 0, -(_MAX_ENTRIES + 1))
    # Reset TTL on every write
    await redis.expire(key, _TTL_SECONDS)

    logger.debug("Short-term memory saved: key=%s members=%d", key, await redis.zcard(key))


async def load_memory(user_id: str, session_id: str, top_n: int = 10) -> list[dict]:
    """Load the most recent *top_n* memory entries (newest first)."""
    redis = get_redis()
    key = _build_key(user_id, session_id)

    # ZREVRANGE returns members in reverse order by score (newest first)
    raw = await redis.zrevrange(key, 0, top_n - 1)

    entries: list[dict] = []
    for item in raw:
        try:
            entries.append(json.loads(item))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Corrupted memory entry in key=%s: %s", key, item[:100])
            continue

    return entries


async def delete_memory(user_id: str, session_id: str) -> None:
    """Delete the entire short-term memory for a session."""
    redis = get_redis()
    key = _build_key(user_id, session_id)
    await redis.delete(key)


async def format_context(entries: list[dict]) -> str:
    """Format a list of memory entries into a compact context string.

    Uses the first 30 characters of each entry's "query" field as a topic.
    """
    topics: list[str] = []
    for entry in entries:
        query: str = entry.get("query", "") if isinstance(entry, dict) else ""
        topic = query[:30].strip()
        if topic:
            topics.append(topic)
    if not topics:
        return ""
    return f"用户最近关注的主题：{', '.join(topics)}"
