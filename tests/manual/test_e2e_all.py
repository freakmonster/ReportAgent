"""End-to-end benchmark: 3 workflows × 3 rounds, collects per-node and total timing.

Usage:
    python tests/manual/test_e2e_all.py

Requires the server to be ALREADY RUNNING on port 8010:
    ./.venv/Scripts/Activate.ps1
    python app.py

Each deep_report / earnings_analysis round takes ~6 min. Total ~40 min.
"""

from __future__ import annotations

import http.client
import json
import sys
import time
from collections import defaultdict

SERVER_HOST = "localhost"
SERVER_PORT = 8010
API_KEY = "dev-secret-key-change-in-production"

WORKFLOWS = {
    "flash_news": "2026年7月AI行业重要动态",
    "deep_report": "2026年7月AI行业重要动态",
    "earnings_analysis": "2026年7月AI行业重要动态",
}
ROUNDS = 1


def run_one(workflow: str, query: str, round_idx: int) -> dict:
    """Run a single workflow test and return timing data."""
    conv_id = f"e2e-bench-{workflow}-{round_idx}"
    body = json.dumps({
        "query": query,
        "report_type": workflow,
        "conversation_id": conv_id,
        "user_id": "u1",
    })

    print(f"\n{'='*60}")
    print(f"  [{workflow}] round {round_idx + 1}/{ROUNDS}  conv_id={conv_id}")
    print(f"{'='*60}")

    t_start = time.time()
    conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=600)
    conn.request(
        "POST", "/chat/stream",
        body=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
    )
    resp = conn.getresponse()

    elapsed_seconds = 0.0
    report_len = 0
    status = resp.status

    while True:
        line = resp.readline().decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data: "):
            continue
        payload = line[6:]
        d = json.loads(payload)
        evt = d.get("event", "")
        if evt == "progress":
            node = d.get("node", "?")
            # Progress ticker
            sys.stdout.write(f"  [{node}] .\n")
            sys.stdout.flush()
        elif evt == "complete":
            data = d.get("data", {})
            report_len = len(data.get("report", ""))
            elapsed_seconds = data.get("elapsed_seconds", 0)
            print(f"  [DONE] elapsed={elapsed_seconds}s  report_len={report_len}")
            break
        elif evt == "error":
            print(f"  [ERROR] {d.get('data', {}).get('message', 'unknown')}")
            break

    conn.close()
    wall_time = time.time() - t_start

    return {
        "workflow": workflow,
        "round": round_idx,
        "status": status,
        "elapsed_sse": elapsed_seconds,
        "wall_time": round(wall_time, 1),
        "report_len": report_len,
    }


def main():
    # -- check server availability --
    print(f"Checking server at {SERVER_HOST}:{SERVER_PORT} ...")
    try:
        conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        conn.close()
        if resp.status != 200:
            print(f"Server returned {resp.status}. Is it ready?")
            sys.exit(1)
        print(f"Server OK (HTTP {resp.status}).")
    except Exception as exc:
        print(f"Cannot reach server: {exc}")
        sys.exit(1)

    all_results: list[dict] = []

    for wf_name, wf_query in WORKFLOWS.items():
        print(f"\n{'#'*60}")
        print(f"  WORKFLOW: {wf_name}  ({ROUNDS} rounds)")
        print(f"{'#'*60}")
        for r in range(ROUNDS):
            result = run_one(wf_name, wf_query, r)
            all_results.append(result)
            # Cooldown between runs
            if r < ROUNDS - 1:
                print("  (cooling down 3s...)")
                time.sleep(3)

    # ── Aggregate & print summary ──────────────────────────────
    print("\n\n")
    print("=" * 70)
    print("  BENCHMARK SUMMARY")
    print("=" * 70)

    # Per-workflow totals
    totals: dict[str, list[float]] = defaultdict(list)
    for r in all_results:
        if r["status"] == 200:
            totals[r["workflow"]].append(r["elapsed_sse"])

    print(f"\n{'Workflow':<22} {'Rounds':>6} {'Avg (s)':>10} {'Min (s)':>10} {'Max (s)':>10}")
    print("-" * 62)
    for wf in ("flash_news", "deep_report", "earnings_analysis"):
        vals = totals.get(wf, [])
        if vals:
            avg = sum(vals) / len(vals)
            print(f"  {wf:<20} {len(vals):>6} {avg:>10.1f} {min(vals):>10.1f} {max(vals):>10.1f}")
        else:
            print(f"  {wf:<20} {'N/A':>6} {'N/A':>10} {'N/A':>10} {'N/A':>10}")

    print()
    print("Per-node timing is available in the server terminal output ([timing] lines).")
    print("Copy those lines here for per-node breakdown.")


if __name__ == "__main__":
    main()
