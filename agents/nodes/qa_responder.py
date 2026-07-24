"""QA Responder node — direct LLM answer for general questions.

Called by the ``qa`` workflow template when the intent classifier
detects a CHAT intent.  Calls DeepSeek Chat API directly with
a friendly system prompt, no search / analysis / review involved.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.state import ReportState

logger = logging.getLogger(__name__)


async def entry(state: ReportState) -> dict[str, Any]:
    """Generate a direct LLM answer for a general question.

    Reads ``base.user_input`` and ``base.session_id`` from state.
    Calls DeepSeek Chat API with a 3-tier fallback chain:
    1. Primary call (deepseek-flash, max_tokens=2000)
    2. Retry (lower temperature 0.3)
    3. Template fallback

    Writes the answer to ``writing.final_content`` and saves a
    summary to Redis short-term memory for multi-turn context.
    """
    user_input: str = state.get("base", {}).get("user_input", "")
    session_id: str = state.get("base", {}).get("session_id", "")
    user_id: str = state.get("base", {}).get("user_id", "anonymous")
    model: str = state.get("base", {}).get("model", "deepseek-flash")

    if not user_input.strip():
        return _no_input_result()

    # ── Load session memory ────────────────────────────────────────
    memory_context = ""
    try:
        from infrastructure.memory.short_term import load_memory

        memories = await load_memory(user_id, session_id)
        if memories:
            memory_context = "用户最近关注的主题：\n" + "\n".join(
                f"- {m}" for m in memories[-5:]  # 最近 5 条
            )
    except Exception as exc:
        logger.warning("qa_responder: load_memory failed | %s", exc)

    # ── Build messages ─────────────────────────────────────────────
    system_prompt = """
        "你是"智能研报生成系统"的智能助手，服务于用户的金融研究与报告生成需求。\n"
        "你的名字是"研究助手"，由本系统提供技术支持。\n"
        "当用户询问"你是谁"或身份相关问题时，明确说明你的身份和定位。\n"
        "\n"
        "你能帮用户做什么：\n"
        "1. 深度研报 — 对行业/公司/市场进行多维度深度分析，输出结构化研报\n"
        "2. 市场快讯 — 快速整理当日行业动态与热点速览\n"
        "3. 财报分析 — 解读公司财报、季报、年报的核心数据与趋势\n"
        "4. 一般问答 — 回答金融、科技、市场等领域的常识性问题\n"
        "\n"
        "回答规则：\n"
        "- 用简洁清晰的中文回答，控制在 500 字以内\n"
        "- 专业问题提供准确信息，不确定时坦诚说明\n"
        "- 不要自我贬低或过度自夸，保持专业、有帮助的态度\n"
        "- 不属于上述能力范围内的问题（如订餐、发送邮件等），礼貌说明无法处理"
        "\n"
        "请根据用户的问题，选择最符合要求的回答。\n"
    """
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    # ── LLM call with 3-tier fallback ──────────────────────────────
    answer = await _try_llm_chat(messages, model)
    if answer is None:
        answer = await _try_llm_chat(messages, model, temperature=0.3)
    if answer is None:
        answer = f"抱歉，暂时无法回答您的问题。请稍后再试或换个问题。（当前模型：{model}）"

    # ── Save session memory ────────────────────────────────────────
    try:
        import asyncio

        from infrastructure.memory.short_term import save_memory

        summary = user_input[:80]
        asyncio.create_task(save_memory(user_id, session_id, summary))
    except Exception as exc:
        logger.warning("qa_responder: save_memory failed | %s", exc)

    return {"writing": {"final_content": answer}}


async def _try_llm_chat(
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.7,
) -> str | None:
    """Try calling DeepSeek Chat API. Returns None on failure."""
    try:
        from models.llm_providers.deepseek_client import DeepSeekClient

        client = DeepSeekClient()
        response = await client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=2000,
        )
        content: str = response["choices"][0]["message"]["content"]
        return content.strip()
    except Exception as exc:
        logger.warning(
            "qa_responder: LLM call failed | model=%s temp=%s | %s",
            model, temperature, exc,
        )
        return None


def _no_input_result() -> dict[str, Any]:
    return {"writing": {"final_content": "请输入您的问题。"}}
