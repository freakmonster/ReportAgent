"""Quick check: Redis version and Stream support."""
import asyncio

import redis.asyncio


async def main():
    r = redis.asyncio.Redis(host="localhost", port=6379, protocol=2)
    try:
        await r.ping()
        info = await r.execute_command("INFO", "server")
        for line in info[b"redis_version"].split(b"\r\n"):
            if b"redis_version" in line:
                print(line.decode())
        # Test Stream support
        try:
            await r.execute_command("XADD", "test_stream", "*", "key", "val")
            print("XADD: OK (Streams supported)")
            await r.execute_command("DEL", "test_stream")
        except Exception as e:
            print(f"XADD: FAILED - {e}")
    finally:
        await r.close()

asyncio.run(main())
