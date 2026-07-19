"""Manual E2E test of flash_news workflow via SSE."""
import http.client
import json

def main():
    body = json.dumps({
        "query": "2026年7月AI行业重要动态",
        "report_type": "deep_report",
        "conversation_id": "e2e-test-006",
        "user_id": "u1"
    })
    conn = http.client.HTTPConnection("localhost", 8010, timeout=120)
    conn.request(
        "POST", "/chat/stream",
        body=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "dev-secret-key-change-in-production"
        }
    )
    resp = conn.getresponse()
    print(f"HTTP {resp.status}")

    while True:
        line = resp.readline().decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data: "):
            continue
        payload = line[6:]
        d = json.loads(payload)
        evt = d.get("event", "")
        if evt == "progress":
            node = d.get("node", "?")
            status = d.get("data", {}).get("status", "?")
            print(f"  [{node}] {status}")
        elif evt == "complete":
            rp = d.get("data", {}).get("report", "N/A")
            print(f"  [DONE] report_length={len(rp)} chars")
            # Print first 500 chars
            if len(rp) > 50:
                print("  --- FULL REPORT ---")
                print(rp)
                print("  --- END ---")
            else:
                print(f"  Report too short: {rp}")
            break

    conn.close()

if __name__ == "__main__":
    main()
