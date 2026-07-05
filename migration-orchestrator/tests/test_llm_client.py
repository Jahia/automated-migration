"""Direct LLM client tests (P5.5).

No real network: every request is served by an httpx.MockTransport. Asserts:
  (a) a normal completion returns (message, usage) and passes response_format
      + tools through the request body;
  (b) transport faults (ConnectError) are retried up to max_retries, then raise;
  (c) an HTTP 4xx is NEVER retried — it raises immediately with the status code;
  (d) a missing API key raises before any request is made;
  (e) the Authorization header carries the key.
"""
from __future__ import annotations

import json

import httpx
import pytest

from src.llm_client import LLMClient, LLMError


def _client(handler, *, api_key="test-key", max_retries=3):
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url="https://example.test/v1", transport=transport, timeout=None)
    return LLMClient(base_url="https://example.test/v1", model="test-model",
                     api_key=api_key, max_retries=max_retries, http=http)


@pytest.mark.asyncio
async def test_chat_returns_message_and_usage_and_passes_format():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "prompt_cache_hit_tokens": 4},
        })

    client = _client(handler)
    msg, usage = await client.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
        response_format={"type": "json_object"},
    )
    assert msg["content"] == "hello"
    assert usage["prompt_tokens"] == 10
    # request body carried model, response_format, tools + tool_choice
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["tools"][0]["function"]["name"] == "read_file"
    assert seen["body"]["tool_choice"] == "auto"
    # key rides the Authorization header
    assert seen["auth"] == "Bearer test-key"
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_is_retried_then_raises():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler, max_retries=2)
    with pytest.raises(LLMError) as ei:
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    # initial try + 2 retries = 3 attempts
    assert calls["n"] == 3
    assert "transport error" in str(ei.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_recovers_within_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {},
        })

    client = _client(handler, max_retries=3)
    msg, usage = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert msg["content"] == "ok"
    assert calls["n"] == 2  # failed once, succeeded on retry
    await client.aclose()


@pytest.mark.asyncio
async def test_http_4xx_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    client = _client(handler, max_retries=3)
    with pytest.raises(LLMError) as ei:
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 1  # NO retry on a status error
    assert ei.value.status_code == 400
    await client.aclose()


@pytest.mark.asyncio
async def test_http_401_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="unauthorized")

    client = _client(handler, max_retries=3)
    with pytest.raises(LLMError) as ei:
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 1
    assert ei.value.status_code == 401
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_api_key_raises_before_request():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {}}], "usage": {}})

    # explicit empty key (not None → not falling through to settings)
    client = _client(handler, api_key="")
    with pytest.raises(LLMError) as ei:
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 0  # no request attempted
    assert "ORCHESTRATOR_LLM_API_KEY" in str(ei.value)
    await client.aclose()
