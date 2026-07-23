"""Chat router — SSE streaming endpoint for report generation.

Executes LangGraph workflow and streams real progress events per node.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from agents.state import ReportState, create_initial_state
from api.middlewares.auth import auth_dependency
from api.schemas.request import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest, user_id: str = Depends(auth_dependency)):
    """SSE streaming endpoint for real-time report generation."""
    workflow_id = body.conversation_id or str(uuid4())
    template = body.report_type or "deep_report"
    session_id = body.session_id or ""

    async def event_generator():
        t_start = time.time()
        print(
            f"[CHAT_START] workflow_id={workflow_id} | user={user_id} | template={template} | model={body.model}",
            file=sys.stderr,
            flush=True,
        )
        try:
            from agents.workflows.builder import WorkflowBuilder

            builder = WorkflowBuilder()
            harness = getattr(request.app.state, "harness_orchestrator", None)
            checkpointer = getattr(request.app.state, "checkpointer", None)
            graph = builder.build(
                template,
                ReportState,
                harness_orchestrator=harness,
                checkpointer=checkpointer,
            )
            state = create_initial_state(
                workflow_id, user_id, template, model=body.model, session_id=session_id
            )
            state["base"]["user_input"] = body.query

            # Accumulate all partial state updates
            merged = {"writing": {}, "base": {}}

            thread_config = {"configurable": {"thread_id": workflow_id}}
            async for event in graph.astream(state, config=thread_config, stream_mode="updates"):
                if await request.is_disconnected():
                    break
                for node_name, node_output in event.items():
                    print(
                        f"[SSE_EVENT] node={node_name} keys={list(node_output.keys())}",
                        file=sys.stderr,
                        flush=True,
                    )
                    yield _event_dict("progress", node_name, {"status": "completed"})
                    # Deep-merge the node output into the accumulator
                    for key in ("writing", "base"):
                        if key in node_output:
                            merged[key].update(node_output[key])

            # Read final_content from the accumulated state
            report = merged.get("writing", {}).get("final_content", "")

            elapsed = time.time() - t_start
            print(
                f"[SSE] workflow_id={workflow_id} template={template} elapsed={elapsed:.1f}s report_len={len(report)}",
                flush=True,
            )

            # Increment report count for the session
            if session_id:
                try:
                    from infrastructure.database.repositories.session_repo import get_session_repo

                    repo = get_session_repo()
                    await repo.increment_report_count(session_id)
                    # Auto-title: first 30 chars of user query if still placeholder
                    await repo.update_title_if_placeholder(
                        session_id, body.query[:30].strip()
                    )
                    print(
                        f"[SSE] session report_count incremented | session={session_id}",
                        file=sys.stderr,
                        flush=True,
                    )
                except Exception as repo_err:
                    print(
                        f"[SSE] failed to increment report_count: {repo_err}",
                        file=sys.stderr,
                        flush=True,
                    )

            complete_data = {
                "workflow_id": workflow_id,
                "report_type": template,
                "elapsed_seconds": round(elapsed, 1),
            }
            if report:
                complete_data["report"] = report

            # 写入 workflow_info 表（运营面板数据源 + 会话历史）
            try:
                import json as _json

                from infrastructure.database.repositories.usage_repo import get_usage_repo

                query_text = str(state.get("base", {}).get("user_input", ""))
                citations_raw = merged.get("writing", {}).get("citation_list", [])
                citations_list = citations_raw if isinstance(citations_raw, list) else []
                # 确保 report_content 是字符串
                report_content = report if isinstance(report, str) else _json.dumps(report, ensure_ascii=False) if report else ""

                print(
                    f"[chat] writing workflow_info | wid={workflow_id} qlen={len(query_text)} rlen={len(report_content)} cit={len(citations_list)}",
                    file=sys.stderr, flush=True,
                )

                await get_usage_repo().record_workflow_info(
                    workflow_id=workflow_id,
                    user_id=user_id,
                    template_name=template,
                    status="published",
                    session_id=session_id or None,
                    started_at=t_start,
                    duration_seconds=elapsed,
                    query=query_text,
                    report_content=report_content,
                    citations=citations_list,
                )
                print(f"[chat] workflow_info recorded | {workflow_id}", file=sys.stderr, flush=True)
            except Exception as rec_err:
                import traceback
                print(
                    f"[chat] failed to record workflow_info: {rec_err}",
                    file=sys.stderr, flush=True,
                )
                traceback.print_exc(file=sys.stderr)

            # 记录工作流耗时到 Redis 统计
            try:
                import asyncio as _asyncio

                from infrastructure.memory.stats import record_workflow_duration

                model = state.get("base", {}).get("model", "deepseek-flash")
                _asyncio.create_task(record_workflow_duration(model, elapsed))
                print(
                    f"[chat] workflow duration recorded | model={model} | {elapsed:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
            except Exception:
                pass

            yield _event_dict("complete", "done", complete_data)

        except Exception as exc:
            print(
                f"[CHAT_ERROR] workflow_id={workflow_id} | error={exc}",
                file=sys.stderr,
                flush=True,
            )
            logger.exception("Workflow failed: %s", workflow_id)
            yield _event_dict("error", "error", {"message": str(exc)})

    return EventSourceResponse(event_generator(), media_type="text/event-stream")


def _event_dict(event: str, node: str, data: dict) -> dict:
    """Build an SSE event dict for sse-starlette native handling.

    sse-starlette v3+ treats yielded dicts as ServerSentEvent parameters,
    producing standard SSE format: ``event: <type>\\ndata: <json>\\n\\n``.
    """
    payload = dict(data)
    payload["node"] = node
    return {
        "event": event,
        "data": json.dumps(payload, ensure_ascii=False),
    }
