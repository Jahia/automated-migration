from __future__ import annotations

import asyncio
import json
import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)


class OpenCodeEventListener:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.opencode_base_url
        self._listeners: dict[str, list[asyncio.Queue]] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        log.info("OpenCode event listener started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("OpenCode event listener stopped")

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        listeners = self._listeners.get(session_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and session_id in self._listeners:
            del self._listeners[session_id]

    async def _listen_loop(self) -> None:
        while self._running:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", f"{self.base_url}/event") as response:
                        buffer = ""
                        async for chunk in response.aiter_bytes():
                            text = chunk.decode("utf-8", errors="replace")
                            buffer += text
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                line = line.strip()
                                if not line:
                                    continue
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    try:
                                        event = json.loads(data_str)
                                        await self._dispatch(event)
                                    except json.JSONDecodeError:
                                        log.warning(f"Failed to parse SSE data: {data_str[:100]}")
            except (httpx.ConnectError, httpx.ReadError) as e:
                log.warning(f"OC SSE connection error: {e}, retrying in 2s...")
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"OpenCode SSE listener error: {e}, retrying in 5s...")
                await asyncio.sleep(5)

    async def _dispatch(self, event: dict) -> None:
        payload = event.get("payload", event)

        session_id = None
        props = payload.get("properties", {})
        if isinstance(props, dict):
            session_id = props.get("sessionID")

        if not session_id:
            info = props.get("info", {})
            if isinstance(info, dict):
                session_id = info.get("sessionID")

        if session_id and session_id in self._listeners:
            for queue in self._listeners[session_id]:
                await queue.put(payload)
