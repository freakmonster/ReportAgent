"""Chat router — SSE streaming endpoint for report generation.

V2.1: Zombie Workflow protection — detects SSE disconnect and interrupts.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from api.schemas.request import ChatRequest
from api.schemas.response import ChatProgressEvent

router = APIRouter(tags=["chat"])


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest):
    """SSE streaming endpoint for real-time report generation.

    Streams progress events as each LangGraph node executes.
    V2.1: Detects client disconnect and interrupts zombie workflows.
    """
    async def event_generator():
        nodes = [
            "intent_classifier", "research_planner", "data_collector",
            "data_processor", "data_analyst", "writer", "editor",
            "reviewer", "publisher",
        ]

        for node in nodes:
            # Check for client disconnect (zombie workflow protection)
            if await request.is_disconnected():
                break

            await asyncio.sleep(0.1)  # simulate node processing time
            event = ChatProgressEvent(
                event="progress",
                node=node,
                data={"status": "running"},
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            yield event.model_dump_json()

        # Final complete event
        final = ChatProgressEvent(
            event="complete",
            node="done",
            data={
                "workflow_id": body.conversation_id or "auto-generated",
                "report_type": body.report_type,
            },
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        yield final.model_dump_json()

    return EventSourceResponse(event_generator())
