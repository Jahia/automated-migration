"""/health endpoint tests (P5.5).

/health must report LLM readiness WITHOUT leaking the key: status ok, a boolean
`configured`, the model and base_url. It no longer reports opencode health.
Tested at the handler level (no lifespan / no network).
"""
from __future__ import annotations

import pytest

from src import main
from src.config import settings


@pytest.mark.asyncio
async def test_health_reports_llm_configured_true(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "secret-value")
    monkeypatch.setattr(settings, "llm_model", "deepseek-v4-flash")
    monkeypatch.setattr(settings, "llm_base_url", "https://api.deepseek.com/v1")
    body = await main.health()
    assert body["status"] == "ok"
    assert body["llm"]["configured"] is True
    assert body["llm"]["model"] == "deepseek-v4-flash"
    assert body["llm"]["base_url"] == "https://api.deepseek.com/v1"
    # the key itself is NEVER in the payload
    assert "secret-value" not in str(body)
    assert "api_key" not in body["llm"]
    assert "key" not in body["llm"]


@pytest.mark.asyncio
async def test_health_reports_llm_configured_false(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", None)
    body = await main.health()
    assert body["status"] == "ok"
    assert body["llm"]["configured"] is False


def test_health_never_mentions_opencode():
    import inspect
    src = inspect.getsource(main.health)
    assert "opencode" not in src.lower()
