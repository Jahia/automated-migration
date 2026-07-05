"""Direct OpenAI-compatible chat client (P5.5 — replaces OpenCode).

The engine no longer proxies through an `opencode serve` process. P5.5b then took
DeepSeek OUT of the control loop entirely: the orchestrator makes NO LLM calls in
nominal operation (deterministic epic approval, retries+idempotence for transients,
decision_pending instead of a repair agent). This client is retained provider-
agnostic for out-of-engine pipeline scripts and any FUTURE in-engine judgment role
that returns; there is currently no call site in the orchestrator.

Provider-agnostic by construction (Julian's non-negotiable): everything flows
through base_url / model / api_key from Settings. Nothing here is DeepSeek-
specific beyond the config DEFAULTS. The endpoint is the OpenAI Chat Completions
shape (`POST {base_url}/chat/completions`), which DeepSeek, OVH, xAI, Mistral,
Together, vLLM, etc. all speak — including tool/function calling and
`response_format`.

Retries are TRANSPORT-only (ConnectError / timeout / read errors) with capped
exponential backoff. An HTTP status response — including 4xx — is NEVER retried:
a 400/401/422 carries a real, deterministic error (bad key, bad request) that a
retry would only repeat, and a tool/verdict error must surface, not be masked.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """A non-retryable failure talking to the LLM API (missing key, HTTP status,
    malformed body). Carries the status code when the fault was an HTTP status."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LLMClient:
    """Minimal async OpenAI-compatible chat client.

    All knobs come from Settings so the provider stays swappable:
      base_url  ORCHESTRATOR_LLM_BASE_URL
      model     ORCHESTRATOR_LLM_MODEL
      api_key   ORCHESTRATOR_LLM_API_KEY   (env only — never a source default)
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        max_retries: int | None = None,
        http: httpx.AsyncClient | None = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        # api_key resolution is deferred to call time via _api_key() so a key set
        # after construction (or via env at restart) is picked up; but an explicit
        # constructor arg wins (used by tests / alternate providers).
        self._api_key_override = api_key
        self.max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        # timeout=None on the client; per-call timeout is passed to each request so
        # a slow judgment call cannot wedge the shared client.
        self.http = http or httpx.AsyncClient(base_url=self.base_url, timeout=None)

    def _api_key(self) -> str | None:
        return self._api_key_override if self._api_key_override is not None else settings.llm_api_key

    @property
    def configured(self) -> bool:
        return bool(self._api_key())

    async def aclose(self) -> None:
        try:
            await self.http.aclose()
        except Exception:  # noqa: BLE001
            pass

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        timeout: float | None = None,
        temperature: float | None = None,
        tool_choice: str | dict | None = None,
    ) -> tuple[dict, dict]:
        """One chat completion. Returns (message, usage):
          message: the assistant message dict (role/content/tool_calls) — the
                   caller inspects .content and .tool_calls.
          usage:   the raw provider usage block (prompt/completion/cache tokens),
                   or {} when the provider omitted it. Fed verbatim to the ledger.

        Raises LLMError on a missing key or any HTTP status error (no retry) and
        on a malformed body. Transport faults are retried up to max_retries.
        """
        key = self._api_key()
        if not key:
            raise LLMError(
                "ORCHESTRATOR_LLM_API_KEY is not set — the engine has no LLM credentials "
                "(copy it into migration-orchestrator/.env; see .env.example)."
            )

        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        elif tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if response_format is not None:
            payload["response_format"] = response_format
        if temperature is not None:
            payload["temperature"] = temperature

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        req_timeout = timeout if timeout is not None else settings.llm_timeout

        attempt = 0
        while True:
            try:
                resp = await self.http.post(
                    "/chat/completions", json=payload, headers=headers, timeout=req_timeout
                )
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                    httpx.ReadError, httpx.WriteError, httpx.PoolTimeout,
                    httpx.RemoteProtocolError) as e:
                # Transport-level fault — retry with capped backoff.
                attempt += 1
                if attempt > self.max_retries:
                    raise LLMError(f"LLM transport error after {self.max_retries} retries: {e}") from e
                backoff = min(2.0 ** (attempt - 1), 8.0)
                log.warning(f"LLM transport error ({e}); retry {attempt}/{self.max_retries} in {backoff:.1f}s")
                await asyncio.sleep(backoff)
                continue

            # An HTTP status response is authoritative — never retried (4xx is a
            # deterministic error; 5xx is surfaced so a real fault isn't masked).
            if resp.status_code >= 400:
                body = (resp.text or "")[:800]
                raise LLMError(
                    f"LLM API returned HTTP {resp.status_code}: {body}",
                    status_code=resp.status_code,
                )

            try:
                data = resp.json()
            except Exception as e:  # noqa: BLE001
                raise LLMError(f"LLM API returned non-JSON body: {(resp.text or '')[:400]}") from e

            choices = data.get("choices") or []
            if not choices:
                raise LLMError(f"LLM API returned no choices: {str(data)[:400]}")
            message = choices[0].get("message") or {}
            usage = data.get("usage") or {}
            return message, usage
