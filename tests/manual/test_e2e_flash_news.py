"""Manual end-to-end test: flash_news workflow."""
import json
import sys

import httpx

body = {
    "query": "2026年7月AI行业重要动态",
    "report_type": "flash_news",
    "conversation_id": "test-py-001",
    "user_id": "u1"
}

with httpx.Client(timeout=120) as client:
    with client.stream(
        "POST",
        "http://localhost:8000/chat/stream",
        json=body,
        headers={"X-API-Key": "dev-secret-key-change-in-production"},
    ) as r:
        for line in r.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            data = json.loads(payload)
            evt = data.get("event", "")
            if evt == "progress":
                node = data.get("node", "?")
                status = data.get("data", {}).get("status", "?")
                print(f"  [{node}] {status}")
            elif evt == "complete":
                report = data.get("data", {}).get("report", "")
                print(f"\n[DONE] report_length={len(report)} chars")
                # Print first 600 chars of decoded report
                decoded = report[:600]
                print(decoded)
                print("...")
                break
