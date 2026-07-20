"""Check connectivity to PostgreSQL, Redis, and Qdrant.

Usage:
    python scripts/check_services.py
"""

import asyncio
import sys


async def check_postgres() -> tuple[bool, str]:
    """Check PostgreSQL connectivity + research_agent database."""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            "postgresql://postgres:postgres@localhost:5432/postgres",
            timeout=5,
        )
        ver = await conn.fetchval("SELECT version()")
        dbs = await conn.fetch("SELECT datname FROM pg_database WHERE datname = 'research_agent'")
        await conn.close()

        db_ok = bool(dbs)
        version_str = ver.split(",")[0] if ver else "unknown"
        if db_ok:
            return True, f"{version_str} (research_agent exists)"
        else:
            return False, f"{version_str} — MISSING: 'research_agent' database"
    except Exception as exc:
        return False, str(exc)


async def check_redis() -> tuple[bool, str]:
    """Check Redis connectivity."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.Redis(host="localhost", port=6379, protocol=2)
        await r.ping()
        await r.aclose()
        return True, "PONG"
    except Exception as exc:
        return False, str(exc)


async def check_qdrant() -> tuple[bool, str]:
    """Check Qdrant connectivity."""
    try:
        from qdrant_client import QdrantClient

        c = QdrantClient(host="localhost", port=6333, timeout=5)
        collections = c.get_collections()
        count = len(collections.collections)
        return True, f"{count} collection(s)"
    except Exception as exc:
        return False, str(exc)


async def main() -> int:
    print("=" * 50)
    print("  Service Connectivity Check")
    print("=" * 50)
    print()

    checks = [
        ("PostgreSQL", check_postgres()),
        ("Redis", check_redis()),
        ("Qdrant", check_qdrant()),
    ]

    all_ok = True
    for name, coro in checks:
        ok, detail = await coro
        status = "\033[92mOK\033[0m" if ok else "\033[91mFAIL\033[0m"
        print(f"  [{status}] {name}: {detail}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("  All services ready. Run: uvicorn app:app")
    else:
        print("  Fix the above issues before starting the app.")
    print("=" * 50)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
