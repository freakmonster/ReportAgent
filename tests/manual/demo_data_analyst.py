"""演示脚本 — 测试 data_analyst 节点的实际效果。

用法:
    python -m tests.manual.demo_data_analyst

前置条件:
    - EnvConfig.md 中的 DeepSeek API Key 可用（LLM 洞察）
    - MCP Chart Server 运行在 localhost:8003（图表生成，可选，失败会降级）

输出:
    - 数字提取结果
    - LLM 生成的洞察（需 API Key）
    - MCP 图表状态（需 Chart Server）
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.WARNING,
    format="[%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.state import create_initial_state

# ── 模拟一个数据收集器输出的 raw_docs ──────────────────────────────────────

SAMPLE_DOCS = [
    {
        "title": "苹果Q2财报超预期",
        "url": "https://example.com/finance/1",
        "content": (
            "苹果公司发布2026财年第二季度财报，总营收1200亿美元，同比增长8%。"
            "净利润达到320亿美元，同比增长12%。服务业务收入250亿美元，增长15%。"
            "大中华区营收180亿美元，下降2%。iPhone出货量为5100万部。"
        ),
    },
    {
        "title": "特斯拉毛利率持续下滑",
        "url": "https://example.com/finance/2",
        "content": (
            "特斯拉最新财报显示毛利率降至18.5%，低于市场预期的19.2%。"
            "全球交付量达到52万辆，同比增长25%。总营收280亿美元，增长5%。"
            "运营利润35亿美元，同比下降3%。自由现金流20亿美元。"
        ),
    },
    {
        "title": "腾讯广告业务强势增长",
        "url": "https://example.com/finance/3",
        "content": (
            "腾讯控股公布季度财务数据，总营收1800亿元，同比增长11%。"
            "净利润485亿元，同比增长15%。广告业务收入350亿元，同比增长20%。"
            "微信月活跃用户数达到13.8亿人，同比增长2%。金融科技收入500亿元。"
        ),
    },
    {
        "title": "比亚迪新能源销量创新高",
        "url": "https://example.com/finance/4",
        "content": (
            "比亚迪发布产销快报，月销量突破40万辆，同比增长38%。"
            "全年累计销量达360万辆，提前完成年度目标。"
            "毛利率提升至22%，净利率达到8.7%。海外出口15万辆。"
        ),
    },
    {
        "title": "英伟达AI芯片收入暴增",
        "url": "https://example.com/finance/5",
        "content": (
            "英伟达数据中心业务收入突破450亿美元，同比增长427%。"
            "总营收达到620亿美元，毛利率高达76%。净利润达到330亿美元。"
            "研发投入85亿美元，同比增长40%。H200芯片出货量超过100万片。"
        ),
    },
    {
        "title": "茅台保持高利润增长",
        "url": "https://example.com/finance/6",
        "content": (
            "贵州茅台发布年度报告，营收达到1800亿元，同比增长15%。"
            "净利润950亿元，同比增长19%。毛利率维持在92%的高位。"
            "直销渠道占比提升至45%，i茅台APP贡献了380亿元收入。"
        ),
    },
]


async def main() -> None:
    print("=" * 70)
    print("data_analyst 节点效果演示")
    print("=" * 70)

    # ── Step 1: 构造输入状态 ─────────────────────────────────────────
    state = create_initial_state("demo-analyst", "demo-user")
    state["collection"]["raw_docs"] = SAMPLE_DOCS
    state["collection"]["source_urls"] = [d["url"] for d in SAMPLE_DOCS]

    print(f"\n[Input] {len(SAMPLE_DOCS)} documents, "
          f"{sum(len(d['content']) for d in SAMPLE_DOCS)} chars")

    # -- Step 2: Call data_analyst.entry() --
    from agents.nodes.data_analyst import entry

    print("\n[Calling] data_analyst.entry()...")
    result = await entry(state)
    analysis = result["collection"]["analysis"]

    # -- Step 3: Number extraction --
    print("\n" + "-" * 50)
    print("[Number Extraction]")
    print("-" * 50)
    print(f"  doc_count:     {analysis['doc_count']}")
    print(f"  total_chars:   {analysis['total_chars']}")
    print(f"  data_quality:  {analysis['data_quality']}")
    print(f"  key_metrics:   ({len(analysis['key_metrics'])} unique)")
    for m in analysis["key_metrics"]:
        print(f"    - {m}")

    # -- Step 4: LLM Insights --
    print("\n" + "-" * 50)
    print("[LLM Insights]")
    print("-" * 50)
    insights = analysis.get("insights", [])
    if insights:
        for i, insight in enumerate(insights, 1):
            print(f"  {i}. {insight}")
    else:
        err = analysis.get("_insights_error")
        if err:
            print(f"  [ERROR] {err}")
        else:
            print("  (none - LLM unavailable or no key_metrics)")

    # -- Step 5: MCP Chart --
    print("\n" + "-" * 50)
    print("[MCP Chart]")
    print("-" * 50)
    charts = analysis.get("charts", [])
    if charts:
        for c in charts:
            print(f"  chart_type:  {c.get('chart_type')}")
            print(f"  title:       {c.get('title')}")
            b64_len = len(c.get("image_base64", ""))
            print(f"  base64 len:  {b64_len} chars {'[OK]' if b64_len > 0 else '[EMPTY]'}")
    else:
        err = analysis.get("_charts_error")
        if err:
            print(f"  [ERROR] {err}")
        else:
            print("  (none - MCP server unavailable or insufficient data)")

    # -- Step 6: Full analysis JSON --
    print("\n" + "-" * 50)
    print("[Full analysis fields]")
    print("-" * 50)
    analysis_compact = dict(analysis)
    if "charts" in analysis_compact and analysis_compact["charts"]:
        for c in analysis_compact["charts"]:
            c["image_base64"] = c.get("image_base64", "")[:50] + "..."
    print(json.dumps(analysis_compact, ensure_ascii=False, indent=2))

    print("\n" + "=" * 70)
    print("[DONE] data_analyst demo complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
