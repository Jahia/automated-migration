from __future__ import annotations

import asyncio

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..orchestrator import subscribe_sse, unsubscribe_sse

router = APIRouter()


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str):
    queue = subscribe_sse(run_id)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": event.get("type", "message"), "data": event}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": {"type": "heartbeat"}}
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe_sse(run_id, queue)

    return EventSourceResponse(event_generator())
