"""Compare writer output vs editor output — 走完整 deep_report 工作流，
在 writer 完成后和 editor 完成后分别捕获 chapter_drafts，并排打印差异。

Usage:
    ./.venv/Scripts/Activate.ps1
    python tests/manual/compare_writer_editor.py
"""

from __future__ import annotations

import asyncio
import difflib
import sys
import time

from agents.state import ReportState, create_initial_state
from agents.workflows.builder import WorkflowBuilder


async def main():
    workflow_id = f"compare-{int(time.time())}"
    template = "deep_report"
    user_id = "compare-user"
    print("=" * 70)
    print(f"  Writer vs Editor 对比测试 — {template}")
    print(f"  workflow_id = {workflow_id}")
    print("=" * 70)

    # ── Build workflow ────────────────────────────────────────────────
    builder = WorkflowBuilder()
    graph = builder.build(template, ReportState)

    state = create_initial_state(workflow_id, user_id, template)
    state["base"]["user_input"] = "2026年7月AI行业重要动态"

    # ── Stream and capture intermediate states ────────────────────────
    writer_drafts: dict[str, str] = {}
    editor_drafts: dict[str, str] = {}

    thread_config = {"configurable": {"thread_id": workflow_id}}
    async for event in graph.astream(state, config=thread_config, stream_mode="updates"):
        for node_name, node_output in event.items():
            writing = node_output.get("writing", {})
            chapters = writing.get("chapter_drafts", {})
            if node_name == "writer" and chapters:
                writer_drafts = dict(chapters)
            elif node_name == "editor" and chapters:
                editor_drafts = dict(chapters)

    # ── Print comparison ──────────────────────────────────────────────
    if not writer_drafts:
        print("\n[ERROR] Writer node produced no drafts — workflow may have failed.")
        return
    if not editor_drafts:
        print("\n[WARN] Editor node produced no drafts — using writer output as editor output.")
        editor_drafts = writer_drafts

    all_chapters = sorted(set(writer_drafts.keys()) | set(editor_drafts.keys()))
    print(f"\n{'—— Results: {len(all_chapters)} chapter(s) ——'}")
    print()

    for i, ch in enumerate(all_chapters):
        w_text = writer_drafts.get(ch, "(Missing)")
        e_text = editor_drafts.get(ch, "(Missing)")
        print(f"{'=' * 70}")
        print(f"  Chapter {i + 1}: {ch}")
        print(f"{'=' * 70}")
        print(f"\n  ── Writer (raw) ──  ({len(w_text)} chars)")
        print(f"  {'-' * 64}")
        for line in w_text[:500].split("\n"):
            print(f"  W | {line}")
        if len(w_text) > 500:
            print(f"  ... ({len(w_text) - 500} more chars)")
        print(f"\n  ── Editor (polished) ──  ({len(e_text)} chars)")
        print(f"  {'-' * 64}")
        for line in e_text[:500].split("\n"):
            print(f"  E | {line}")
        if len(e_text) > 500:
            print(f"  ... ({len(e_text) - 500} more chars)")

        # Calculate diff stats
        diff_ratio = difflib.SequenceMatcher(None, w_text, e_text).ratio()
        changed = len(w_text) != len(e_text) or diff_ratio < 1.0
        status = "CHANGED" if changed else "IDENTICAL"
        print(
            f"\n  ── DIFF ──  ratio={diff_ratio:.3f}  status={status}  len: {len(w_text)} → {len(e_text)}"
        )

        # Show actual diff lines
        if changed and len(w_text) < 3000 and len(e_text) < 3000:
            w_lines = w_text.splitlines(keepends=True)
            e_lines = e_text.splitlines(keepends=True)
            diff_lines = list(
                difflib.unified_diff(
                    w_lines,
                    e_lines,
                    fromfile="[Writer]",
                    tofile="[Editor]",
                    lineterm="",
                )
            )
            if diff_lines:
                print(f"  {'-' * 64}")
                for dl in diff_lines[:30]:
                    print(f"  {dl}")
                if len(diff_lines) > 30:
                    print(f"  ... ({len(diff_lines) - 30} more diff lines)")

        print()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
