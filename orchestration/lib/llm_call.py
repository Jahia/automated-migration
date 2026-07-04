#!/usr/bin/env python3
"""llm_call.py — minimal OpenAI-compatible chat client for the PIPELINE scripts.

P5.6 (Julian, 2026-07-04): DeepSeek's real value is HIGH-VOLUME, BOUNDED METADATA
generation — component/zone NAMING, editor-UI field labels + tooltips, exceptions
triage. NEVER site content ("on ne génère jamais de contenu" — the content comes
from the source site only; this client is used exclusively for metadata about the
MODEL and the editor CHROME).

Why a SECOND client (the engine already has migration-orchestrator/src/llm_client.py):
these scripts run OUTSIDE the engine venv (system python3), so they cannot import
`src.*` or depend on httpx/pydantic being installed. This is stdlib-only (urllib)
so it works with a bare `python3`. It is provider-agnostic by construction — the
same three knobs as the engine (base_url / model / api_key), same OpenAI Chat
Completions endpoint (`POST {base_url}/chat/completions`) that DeepSeek/OVH/xAI/
Mistral/vLLM all speak.

Config (env first, then a fallback parse of migration-orchestrator/.env — the KEY
is NEVER printed, NEVER committed):
  ORCHESTRATOR_LLM_BASE_URL   default https://api.deepseek.com/v1
  ORCHESTRATOR_LLM_MODEL      default deepseek-v4-flash
  ORCHESTRATOR_LLM_API_KEY    (gitignored .env / env only — no source default)
  ORCHESTRATOR_LLM_MAX_RETRIES default 3   (TRANSPORT retries only; never 4xx/5xx)
  ORCHESTRATOR_LLM_TIMEOUT     default 180  (per-call, seconds)

Ledger: EVERY call is appended to projects/<project>/llm-usage.jsonl via the shared
orchestration/lib/llm_usage.append_usage (identical JSONL contract as the JS/engine
halves), provider "deepseek-direct", caller passed by the script. A response with
no usage block is STILL logged (nulls + usage_missing) — the call COUNT is exact.

Library:
  client = LLMClient(project_path="projects/foo", caller="name_model.py")
  data = client.chat_json(messages, timeout=..., retries=..., meta={...})
    -> the PARSED json_object (dict). Raises LLMError on missing key / HTTP status
       / unparseable body. Transport faults retried up to max_retries.
  client.chat(messages, response_format=..., ...) -> (message_dict, usage_dict)

CLI (smoke test — prints ONLY model + usage, never the key):
  python3 orchestration/lib/llm_call.py --project projects/foo --smoke
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Shared ledger (Python half). Importable whether run as a module or a script.
try:
    from . import llm_usage  # type: ignore
except Exception:  # noqa: BLE001 — run as a bare script
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import llm_usage  # type: ignore


DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 180.0
PROVIDER = "deepseek-direct"

# Located relative to this file: orchestration/lib/ -> repo root -> the .env.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_ORCH_ENV = os.path.join(_REPO_ROOT, "migration-orchestrator", ".env")


class LLMError(RuntimeError):
    """Non-retryable failure (missing key, HTTP status, malformed body).

    Carries the status code when the fault was an HTTP status. Its str() NEVER
    contains the API key (the key is never placed in a message)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _parse_env_file(path: str) -> dict[str, str]:
    """Parse a dotenv file into a dict. Tolerant: skips blanks/comments, strips
    optional surrounding quotes and an `export ` prefix. Never raises."""
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                if k:
                    out[k] = v
    except Exception:  # noqa: BLE001 — a missing/unreadable .env is not fatal
        pass
    return out


def _resolve(name: str, dotenv: dict[str, str], default=None):
    """Env wins over the dotenv fallback, which wins over the default."""
    val = os.environ.get(name)
    if val is not None and val != "":
        return val
    val = dotenv.get(name)
    if val is not None and val != "":
        return val
    return default


class LLMClient:
    """Minimal stdlib (urllib) OpenAI-compatible chat client for pipeline scripts.

    All knobs come from env / migration-orchestrator/.env so the provider stays
    swappable. The api_key is read but NEVER printed / logged / stored — it lives
    only in the Authorization header of each request.
    """

    def __init__(
        self,
        project_path: str | None = None,
        caller: str = "llm_call.py",
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        max_retries: int | None = None,
        timeout: float | None = None,
        env_file: str | None = None,
    ):
        dotenv = _parse_env_file(env_file or _ORCH_ENV)
        self.project_path = project_path
        self.caller = caller
        self.base_url = str(base_url or _resolve("ORCHESTRATOR_LLM_BASE_URL", dotenv, DEFAULT_BASE_URL)).rstrip("/")
        self.model = str(model or _resolve("ORCHESTRATOR_LLM_MODEL", dotenv, DEFAULT_MODEL))
        # Key: explicit arg > env > .env. Kept private; exposed only via `configured`.
        self._api_key = api_key or _resolve("ORCHESTRATOR_LLM_API_KEY", dotenv, None)
        try:
            self.max_retries = int(max_retries if max_retries is not None
                                   else _resolve("ORCHESTRATOR_LLM_MAX_RETRIES", dotenv, DEFAULT_MAX_RETRIES))
        except (TypeError, ValueError):
            self.max_retries = DEFAULT_MAX_RETRIES
        try:
            self.timeout = float(timeout if timeout is not None
                                 else _resolve("ORCHESTRATOR_LLM_TIMEOUT", dotenv, DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            self.timeout = DEFAULT_TIMEOUT

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    # ── ledger ────────────────────────────────────────────────────────
    def _log(self, usage: dict | None, *, caller: str | None, meta: dict | None,
             usage_missing_forced: bool = False) -> None:
        """Append one ledger record. Never raises into the caller's hot path."""
        if not self.project_path:
            return
        tin, tout, cache, missing = llm_usage.normalize_deepseek_usage(usage)
        try:
            llm_usage.append_usage(
                self.project_path,
                provider=PROVIDER,
                caller=caller or self.caller,
                model=self.model,
                tokens_in=tin, tokens_out=tout, tokens_cache=cache,
                meta=meta or None,
                usage_missing=bool(missing or usage_missing_forced),
            )
        except Exception as e:  # noqa: BLE001
            print(f"[llm_call] ledger append failed: {e}", file=sys.stderr)

    # ── transport ─────────────────────────────────────────────────────
    def chat(
        self,
        messages: list[dict],
        *,
        response_format: dict | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        caller: str | None = None,
        meta: dict | None = None,
    ) -> tuple[dict, dict]:
        """One chat completion. Returns (assistant_message, usage_block).

        EVERY outcome that reaches the provider is ledgered (success OR HTTP
        status error — the latter as a usage_missing record so the count is
        exact). Transport faults (connection reset, timeout, DNS) are retried up
        to max_retries with capped exponential backoff and are NOT ledgered until
        one finally succeeds or the retries are exhausted (a transport fault never
        reached the model, so it consumed no tokens).

        Raises LLMError on: no key, any HTTP status (4xx/5xx — never retried, a
        deterministic error), a malformed / non-JSON body, or exhausted transport
        retries.
        """
        if not self._api_key:
            raise LLMError(
                "ORCHESTRATOR_LLM_API_KEY is not set — no LLM credentials "
                "(put it in migration-orchestrator/.env; see .env.example)."
            )
        n_retries = self.max_retries if retries is None else int(retries)
        to = float(timeout if timeout is not None else self.timeout)

        payload: dict = {"model": self.model, "messages": messages}
        if response_format is not None:
            payload["response_format"] = response_format
        if temperature is not None:
            payload["temperature"] = temperature
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        attempt = 0
        t0 = time.time()
        while True:
            attempt += 1
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=to) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                    status = resp.status
            except urllib.error.HTTPError as e:
                # An HTTP status IS a response — deterministic, NEVER retried.
                # Read the (bounded) error body for diagnostics; NEVER echo headers
                # (they would carry the Authorization we sent).
                try:
                    err_body = e.read().decode("utf-8", "replace")[:800]
                except Exception:  # noqa: BLE001
                    err_body = ""
                self._log(None, caller=caller, meta={**(meta or {}),
                          "status": e.code, "error": "http_status",
                          "duration_ms": int((time.time() - t0) * 1000)},
                          usage_missing_forced=True)
                raise LLMError(f"HTTP {e.code} from LLM API: {err_body}", status_code=e.code) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                # Transport fault — retry with capped backoff. Reason string never
                # contains the key (it is only in the request headers).
                if attempt > n_retries:
                    raise LLMError(f"transport error after {attempt} attempt(s): {e}") from None
                time.sleep(min(2 ** (attempt - 1), 8))
                continue

            # 2xx — parse the OpenAI Chat Completions envelope.
            try:
                data = json.loads(raw)
            except Exception as e:  # noqa: BLE001
                self._log(None, caller=caller, meta={**(meta or {}), "status": status,
                          "error": "unparseable_body"}, usage_missing_forced=True)
                raise LLMError(f"malformed JSON body from LLM API: {e}") from None
            usage = data.get("usage") if isinstance(data, dict) else None
            self._log(usage, caller=caller, meta={**(meta or {}), "status": status,
                      "duration_ms": int((time.time() - t0) * 1000)})
            try:
                message = data["choices"][0]["message"]
            except Exception as e:  # noqa: BLE001
                raise LLMError(f"no message in LLM response: {e}") from None
            return message, (usage or {})

    def chat_json(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        caller: str | None = None,
        meta: dict | None = None,
    ) -> dict:
        """chat() with response_format=json_object, returning the PARSED object.

        The model is asked (and instructed via the caller's system prompt) to emit
        a single JSON object. Raises LLMError if the content is not valid JSON.
        """
        message, _usage = self.chat(
            messages,
            response_format={"type": "json_object"},
            temperature=temperature, timeout=timeout, retries=retries,
            caller=caller, meta=meta,
        )
        content = (message or {}).get("content") or ""
        content = content.strip()
        # Some providers wrap JSON in a ```json fence even in json_object mode.
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else content
            if content.endswith("```"):
                content = content[: -3]
            content = content.strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()
        try:
            return json.loads(content)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"LLM did not return valid JSON: {e}; got: {content[:200]!r}") from None


# ── CLI smoke test (never prints the key) ─────────────────────────────
def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Smoke-test the pipeline LLM client (no key printed).")
    ap.add_argument("--project", default=None, help="projects/<name> (for the ledger)")
    ap.add_argument("--smoke", action="store_true", help="make one tiny real call")
    a = ap.parse_args(argv)

    client = LLMClient(project_path=a.project, caller="llm_call.py:smoke")
    print(f"base_url={client.base_url}")
    print(f"model={client.model}")
    print(f"configured={client.configured}")
    if not a.smoke:
        return 0
    if not client.configured:
        print("ORCHESTRATOR_LLM_API_KEY not set — skipping smoke call (no-op).")
        return 0
    try:
        msg, usage = client.chat(
            [{"role": "user", "content": "Reply with the single word: pong"}],
            timeout=60.0, caller="llm_call.py:smoke",
        )
    except LLMError as e:
        print(f"SMOKE FAILED: {e}")
        return 1
    print(f"usage={usage}")
    print(f"got_content={bool((msg or {}).get('content'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
