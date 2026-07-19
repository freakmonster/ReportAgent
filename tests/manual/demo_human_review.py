"""演示脚本 — 测试 human_review 节点的实际效果。

用法:
    python -m tests.manual.demo_human_review

前置条件:
    - $env:DEEPSEEK_API_KEY 无需设置（human_review 不调用 LLM）

输出:
    - reviewer 决策 → human_review 决策 的过渡效果
    - quality_scores 透传结果
    - human_review_status / review_feedback 字段验证
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


# ── Simulated post-reviewer state ─────────────────────────────────────

QUALITY_SCORES: dict[str, float] = {
    "completeness": 0.85,
    "accuracy": 0.78,
    "citation": 0.70,
    "logic": 0.90,
    "overall": 0.81,
}


async def main() -> None:
    print("=" * 70)
    print("human_review 节点效果演示")
    print("=" * 70)

    # ── Step 1: 构造输入状态（模拟 reviewer 输出） ───────────────────
    from agents.state import create_initial_state

    state = create_initial_state("demo-human-review", "demo-user")
    state["review"]["decision"] = "needs_human"
    state["review"]["quality_scores"] = QUALITY_SCORES
    state["review"]["hallucination_flag"] = False

    review_before: dict = dict(state["review"])

    print("\n[Input — Post-Reviewer State]")
    print(f"  decision:            {review_before['decision']}")
    print(f"  quality_scores:      {QUALITY_SCORES}")
    print(f"  hallucination_flag:  {review_before['hallucination_flag']}")
    print(f"  overall score:       {QUALITY_SCORES['overall']}")

    # ── Step 2: 调用 human_review.entry() ────────────────────────────
    from agents.nodes.human_review import entry

    print("\n[Calling] human_review.entry()...")
    result = await entry(state)

    # ── Step 3: 展示所有新增 / 修改字段 ──────────────────────────────
    review_after: dict = result["review"]
    decision = review_after.get("decision")
    quality_scores = review_after.get("quality_scores", {})
    review_feedback = review_after.get("review_feedback")
    human_review_status = review_after.get("human_review_status")
    base_status = result["base"].get("status")

    print("\n" + "-" * 50)
    print("[Human Review — New / Modified Fields]")
    print("-" * 50)
    print(f"  decision:              {decision}")
    print(f"  quality_scores:        {quality_scores}")
    print(f"  review_feedback:       {review_feedback!r}")
    print(f"  human_review_status:   {human_review_status}")

    # ── Step 4: 决策过渡 ──────────────────────────────────────────────
    print("\n" + "-" * 50)
    print("[Decision Transition]")
    print("-" * 50)
    print(f"  reviewer decision (before):  {review_before['decision']}")
    print(f"  human review (after):        {decision}")

    # ── Step 5: 状态摘要 ─────────────────────────────────────────────
    print("\n" + "-" * 50)
    print("[State Summary]")
    print("-" * 50)
    print(f"  workflow_id:                  {state['base']['workflow_id']}")
    print(f"  base.status:                  {base_status}")
    print(f"  review.decision:              {decision}")
    print(f"  review.human_review_status:   {human_review_status}")
    print(f"  review.review_feedback:       {review_feedback!r}")
    print(f"  review.hallucination_flag:    {review_after.get('hallucination_flag')}")
    print(f"  quality_scores.overall:       {quality_scores.get('overall', 'N/A')}")
    print(f"  quality_scores.completeness:  {quality_scores.get('completeness', 'N/A')}")
    print(f"  quality_scores.accuracy:      {quality_scores.get('accuracy', 'N/A')}")
    print(f"  quality_scores.citation:      {quality_scores.get('citation', 'N/A')}")
    print(f"  quality_scores.logic:         {quality_scores.get('logic', 'N/A')}")

    print("\n" + "=" * 70)
    print("[DONE] human_review demo complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
