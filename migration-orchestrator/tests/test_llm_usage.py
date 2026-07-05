"""Offline tests for the per-project LLM usage ledger (orchestration/lib/llm_usage.py).

No network, no LLM endpoint. Covers: append format, summary math, usage_missing
path, DeepSeek cache mapping, absent/empty ledger, and the engine-cost merge.
"""
import json
import os
import sys
from pathlib import Path

# orchestration/lib lives two levels up from migration-orchestrator/tests
REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "orchestration" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import llm_usage as U  # noqa: E402


def _read(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


# ── ledger_path resolution ──

def test_ledger_path_projects_prefix(tmp_path):
    p = U.ledger_path(str(tmp_path / "projects" / "foo"))
    assert p.endswith(os.path.join("foo", "llm-usage.jsonl"))


def test_ledger_path_bare_name():
    assert U.ledger_path("foo") == os.path.join("projects", "foo", "llm-usage.jsonl")


# ── append format ──

def test_append_writes_full_contract(tmp_path):
    proj = str(tmp_path / "proj-a")
    path = U.append_usage(proj, provider="deepseek", caller="group_llm", model="deepseek-v4-flash",
                          tokens_in=1465, tokens_out=355, tokens_cache=67328,
                          meta={"step": "grouping", "attempt": 1})
    recs = _read(path)
    assert len(recs) == 1
    r = recs[0]
    assert r["provider"] == "deepseek"
    assert r["tokens_in"] == 1465
    assert r["tokens_cache"] == 67328
    assert r["meta"]["step"] == "grouping"
    assert "ts" in r and r["ts"]
    assert "usage_missing" not in r


def test_append_is_append_only(tmp_path):
    proj = str(tmp_path / "proj-b")
    U.append_usage(proj, provider="ovh", caller="c", model="m", tokens_in=1, tokens_out=1, tokens_cache=0)
    U.append_usage(proj, provider="ovh", caller="c", model="m", tokens_in=2, tokens_out=2, tokens_cache=0)
    assert len(_read(U.ledger_path(proj))) == 2


# ── usage_missing path ──

def test_usage_missing_preserves_call_count(tmp_path):
    proj = str(tmp_path / "proj-c")
    U.append_usage(proj, provider="ovh", caller="c", model="m", usage_missing=True)
    r = _read(U.ledger_path(proj))[0]
    assert r["usage_missing"] is True
    assert r["tokens_in"] is None and r["tokens_out"] is None
    # a usage_missing call must still count toward the total
    summary = U.summarize(_read(U.ledger_path(proj)))
    assert summary["total"]["calls"] == 1
    assert summary["total"]["usage_missing"] == 1
    assert summary["total"]["tokens_in"] == 0  # null -> 0 tokens, call still counts


# ── normalize usage ──

def test_normalize_openai_nested_cache():
    tin, tout, cache, missing = U.normalize_openai_usage(
        {"prompt_tokens": 900, "completion_tokens": 100, "prompt_tokens_details": {"cached_tokens": 64}})
    assert (tin, tout, cache, missing) == (900, 100, 64, False)


def test_normalize_deepseek_cache_hit_maps_to_tokens_cache():
    tin, tout, cache, missing = U.normalize_deepseek_usage(
        {"prompt_tokens": 1000, "completion_tokens": 50,
         "prompt_cache_hit_tokens": 640, "prompt_cache_miss_tokens": 360})
    assert tin == 1000  # prompt_tokens already includes hit+miss, not double-counted
    assert tout == 50
    assert cache == 640
    assert missing is False


def test_normalize_none_usage_is_missing():
    assert U.normalize_openai_usage(None) == (None, None, None, True)
    assert U.normalize_deepseek_usage(None) == (None, None, None, True)


# ── summary math ──

def test_summary_per_provider_and_grand_total(tmp_path):
    proj = str(tmp_path / "proj-d")
    U.append_usage(proj, provider="ovh", caller="c", model="m", tokens_in=100, tokens_out=10, tokens_cache=5)
    U.append_usage(proj, provider="ovh", caller="c", model="m", tokens_in=200, tokens_out=20, tokens_cache=0)
    U.append_usage(proj, provider="deepseek", caller="g", model="m", tokens_in=1000, tokens_out=50, tokens_cache=640)
    s = U.summarize(_read(U.ledger_path(proj)))
    assert s["providers"]["ovh"]["calls"] == 2
    assert s["providers"]["ovh"]["tokens_in"] == 300
    assert s["providers"]["ovh"]["tokens_cache"] == 5
    assert s["providers"]["deepseek"]["calls"] == 1
    assert s["total"]["calls"] == 3
    assert s["total"]["tokens_in"] == 1300
    assert s["total"]["tokens_cache"] == 645


# ── absent / empty ledger ──

def test_absent_ledger_is_graceful(tmp_path):
    assert U.read_ledger(str(tmp_path / "nope")) == []
    assert U.summarize([])["total"]["calls"] == 0


def test_empty_and_corrupt_lines_skipped(tmp_path):
    proj = tmp_path / "proj-e"
    proj.mkdir()
    f = proj / "llm-usage.jsonl"
    f.write_text('{"provider":"ovh","tokens_in":5}\n\n   \nNOT JSON\n{"provider":"ovh","tokens_in":5}\n')
    recs = U.read_ledger(str(proj))
    assert len(recs) == 2  # two valid lines, blanks + garbage skipped
    assert U.summarize(recs)["total"]["tokens_in"] == 10


# ── engine-cost merge ──

def test_engine_cost_merge(tmp_path):
    costs = tmp_path / "costs"
    costs.mkdir()
    (costs / "run_1.json").write_text(json.dumps({
        "run_id": "run_1", "model": "opencode/deepseek-v4-flash",
        "total": {"tokens_in": 148430, "tokens_out": 11425, "tokens_cache": 3225472},
    }))
    (costs / "run_2.json").write_text(json.dumps({
        "run_id": "run_2", "model": "opencode/deepseek-v4-flash",
        "total": {"tokens_in": 1000, "tokens_out": 100, "tokens_cache": 500},
    }))
    recs = U.engine_cost_records(str(costs))
    assert len(recs) == 2
    assert all(r["provider"] == U.ENGINE_PROVIDER_LABEL for r in recs)
    s = U.summarize(recs)
    agg = s["providers"][U.ENGINE_PROVIDER_LABEL]
    assert agg["calls"] == 2
    assert agg["tokens_in"] == 149430
    assert agg["tokens_cache"] == 3225972


def test_engine_cost_dir_absent_is_empty(tmp_path):
    assert U.engine_cost_records(str(tmp_path / "nope")) == []


# ── CLI end to end ──

def test_cli_json_output(tmp_path, capsys):
    proj = str(tmp_path / "proj-cli")
    U.append_usage(proj, provider="ovh", caller="c", model="m", tokens_in=7, tokens_out=1, tokens_cache=0)
    rc = U.main([proj, "--json", "--no-engine-costs"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total"]["calls"] == 1
    assert out["total"]["tokens_in"] == 7
