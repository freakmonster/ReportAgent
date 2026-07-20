"""演示脚本 — 测试 editor 节点的实际效果。

用法:
    python -m tests.manual.demo_editor

前置条件:
    - EnvConfig.md 中的 DeepSeek API Key 可用（LLM 润色，可选，失败会降级）

输出:
    - 引用提取与交叉验证结果
    - LLM 润色前后对比（或降级提示）
    - Markdown 规范化效果
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

logging.basicConfig(
    level=logging.WARNING,
    format="[%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)


# ── Simulated writer output (3 chapters, mixed quality) ───────────────

SOURCE_URLS = [
    "https://example.com/report/2025-q1",
    "https://example.com/report/2025-q2",
    "https://example.com/market/overview",
    "https://example.com/competitor/analysis",
]

SIMULATED_CHAPTERS: dict[str, str] = {
    "市场概况": (
        "## 市场概况\n\n"
        "2025年一季度全球新能源汽车销量达380万辆，同比增长22%[1]。"
        "中国市场占比超过60%，比亚迪以38%的市占率继续领跑[2]。\n\n"
        "特斯拉全球交付量52万辆，毛利率回升至18.5%，"
        "FSD V12在中国获批测试许可[1]"
    ),
    "竞争格局": (
        "## 竞争格局\n\n\n\n"  # Extra blank lines for normalization test
        "比亚迪凭借垂直整合优势持续扩大领先地位，"
        "2025年上半年累计销量突破200万辆[2]\n\n\n"
        "特斯拉在全球高端市场保持优势，Model Y仍是全球最畅销车型[1]。\n\n\n\n"
        "小米SU7月销量突破3万辆，成为最大黑马[3]"
    ),
    "风险与展望": (
        "## 风险与展望\n\n"
        "行业面临电池原材料价格波动风险，碳酸锂价格回升至12万元/吨[4]"
        "欧盟对中国电动车加征关税可能影响出口增速\n\n"
        "技术路线方面，固态电池预计2026年进入小批量量产阶段[3]"
    ),
}


async def main() -> None:
    print("=" * 70)
    print("editor 节点效果演示")
    print("=" * 70)

    # ── Step 1: 构造输入状态 ─────────────────────────────────────────
    from agents.state import create_initial_state

    state = create_initial_state("demo-editor", "demo-user")
    state["writing"]["chapter_drafts"] = SIMULATED_CHAPTERS
    state["collection"]["source_urls"] = SOURCE_URLS

    print(f"\n[Input] {len(SIMULATED_CHAPTERS)} chapters, {len(SOURCE_URLS)} source URLs")

    # ── Step 2: 调用 editor.entry() ───────────────────────────────────
    from agents.nodes.editor import entry

    print("\n[Calling] editor.entry()...")
    result = await entry(state)
    edited = result["writing"]["chapter_drafts"]
    citations = result["writing"]["citation_list"]

    # ── Step 3: 引用提取 ──────────────────────────────────────────────
    print("\n" + "-" * 50)
    print("[Citation Extraction]")
    print("-" * 50)
    print(f"  source_urls in:   {len(SOURCE_URLS)}")
    print(f"  citation_list out: {len(citations)}")
    if citations:
        print("  (validated, preserved from source_urls)")
        for i, url in enumerate(citations, 1):
            print(f"  [{i}] {url}")
    else:
        print("  (empty — no citations found, no source_urls)")

    # ── Step 4: 润色前后对比 ──────────────────────────────────────────
    print("\n" + "-" * 50)
    print("[Before / After Polish]")
    print("-" * 50)
    for ch_name in SIMULATED_CHAPTERS:
        before = SIMULATED_CHAPTERS[ch_name][:150].replace("\n", "\\n")
        after = edited[ch_name][:150].replace("\n", "\\n")
        changed = (
            "CHANGED" if edited[ch_name] != SIMULATED_CHAPTERS[ch_name] else "identical (fallback)"
        )
        print(f"\n  --- {ch_name} [{changed}] ---")
        print(f"  BEFORE: {before}...")
        print(f"  AFTER:  {after}...")

    # ── Step 5: 规范化效果 ───────────────────────────────────────────
    print("\n" + "-" * 50)
    print("[Markdown Normalization]")
    print("-" * 50)
    for ch_name in SIMULATED_CHAPTERS:
        text = edited[ch_name]
        blank_3 = text.count("\n\n\n")
        trailing = any(line != line.rstrip() for line in text.split("\n"))
        print(f"  {ch_name}:")
        print(f"    3+ consecutive blank lines: {blank_3}  (should be 0)")
        print(f"    trailing whitespace:        {'YES' if trailing else 'NONE'}")

    # ── Step 6: 完整编辑后文本 ───────────────────────────────────────
    print("\n" + "-" * 50)
    print("[Edited Chapters (first 200 chars)]")
    print("-" * 50)
    for ch_name, content in edited.items():
        preview = content[:200].replace("\n", "\\n")
        print(f"  [{ch_name}] {preview}...")

    # ── Step 7: 全量 state 摘要 ───────────────────────────────────────
    print("\n" + "-" * 50)
    print("[Summary]")
    print("-" * 50)
    print(f"  chapters edited: {len(edited)}")
    print(f"  citations validated: {len(citations)}")
    for ch_name in edited:
        before_len = len(SIMULATED_CHAPTERS[ch_name])
        after_len = len(edited[ch_name])
        print(f"  [{ch_name}] {before_len} → {after_len} chars")

    print("\n" + "=" * 70)
    print("[DONE] editor demo complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
