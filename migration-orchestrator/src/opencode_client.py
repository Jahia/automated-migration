from __future__ import annotations

import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)


class OpenCodeClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.opencode_base_url
        self.http = httpx.AsyncClient(base_url=self.base_url, timeout=None)

    async def health(self) -> dict:
        resp = await self.http.get("/global/health")
        resp.raise_for_status()
        return resp.json()

    async def list_agents(self, directory: str | None = None) -> list[dict]:
        params = {}
        if directory:
            params["directory"] = directory
        resp = await self.http.get("/agent", params=params)
        resp.raise_for_status()
        return resp.json()

    async def create_session(self, title: str = "", directory: str | None = None) -> dict:
        params = {}
        if directory:
            params["directory"] = directory
        resp = await self.http.post("/session", json={"title": title}, params=params)
        resp.raise_for_status()
        return resp.json()

    async def send_prompt_async(self, session_id: str, prompt: str, agent: str = "code", directory: str | None = None) -> None:
        params = {}
        if directory:
            params["directory"] = directory
        await self.http.post(
            f"/session/{session_id}/prompt_async",
            json={
                "parts": [{"type": "text", "text": prompt}],
                "agent": agent,
            },
            params=params,
        )

    async def send_message(self, session_id: str, text: str, directory: str | None = None) -> dict:
        params = {}
        if directory:
            params["directory"] = directory
        resp = await self.http.post(
            f"/session/{session_id}/message",
            json={"parts": [{"type": "text", "text": text}]},
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_messages(self, session_id: str) -> list[dict]:
        resp = await self.http.get(f"/session/{session_id}/message")
        resp.raise_for_status()
        return resp.json()

    async def respond_permission(self, session_id: str, permission_id: str, response: str = "always") -> None:
        await self.http.post(
            f"/session/{session_id}/permissions/{permission_id}",
            json={"response": response},
        )
