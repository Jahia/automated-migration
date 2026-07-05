#!/usr/bin/env python3
"""llm_usage.py — centralized per-project LLM usage ledger (Python side).

Julian's standing requirement: EVERY OVH vision call and EVERY DeepSeek call is
accounted for, per project. This is the Python half of the ledger (the JS half is
orchestration/lib/llm_ledger.mjs — identical JSONL contract).

Contract — append-only JSONL at  projects/<p>/llm-usage.jsonl  (PROJECT ROOT, NOT
workflow-output, so it SURVIVES pipeline resets). One line per LLM call:
  {"ts": <iso8601>, "provider": "ovh"|"deepseek", "caller": "<tool[:detail]>",
   "model": "...", "tokens_in": n|null, "tokens_out": n|null, "tokens_cache": n|null,
   "meta": {...optional...} [, "usage_missing": true]}
A response missing its usage block is STILL logged (nulls + usage_missing:true) —
the call COUNT must always be exact.

Library:
  append_usage(project_path, provider=..., caller=..., model=..., tokens_in=...,
               tokens_out=..., tokens_cache=..., meta={...}, usage_missing=False)
  normalize_openai_usage(usage)   -> (tokens_in, tokens_out, tokens_cache, missing)
  normalize_deepseek_usage(usage) -> (…)  # maps prompt_cache_hit_tokens -> cache

CLI:
  python3 orchestration/lib/llm_usage.py projects/<p> [--json] [--no-engine-costs]
prints, per provider: number of calls + total tokens_in/out/cache, then grand
totals. Also MERGES the engine's opencode cost reports (migration-orchestrator/
costs/run_*.json) as a synthetic provider "deepseek (opencode agents)" — the
engine's per-run usage does not carry a project (would need an off-limits
orchestrator.py edit to route per-project), so it is reported at repo scope,
honestly labelled. Pass --no-engine-costs to omit it.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

LEDGER_BASENAME = "llm-usage.jsonl"
ENGINE_PROVIDER_LABEL = "deepseek (opencode agents)"


# ── library ───────────────────────────────────────────────────────

def ledger_path(project_path: str) -> str:
    """Resolve projects/<p>/llm-usage.jsonl for any project pointer.

    A bare name (no separator) is treated as living under projects/.
    """
    if not project_path:
        raise ValueError("project_path is required")
    p = str(project_path).strip().rstrip("/")
    if "/" not in p and os.sep not in p:
        p = os.path.join("projects", p)
    return os.path.join(p, LEDGER_BASENAME)


def normalize_openai_usage(usage: dict | None):
    """OpenAI/OVH-shaped usage -> (tokens_in, tokens_out, tokens_cache, missing)."""
    if not isinstance(usage, dict):
        return None, None, None, True
    tin = usage.get("prompt_tokens", usage.get("input_tokens"))
    tout = usage.get("completion_tokens", usage.get("output_tokens"))
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    cache = (
        (details.get("cached_tokens") if isinstance(details, dict) else None)
        or usage.get("cached_tokens")
        or usage.get("prompt_cache_hit_tokens")
    )
    missing = tin is None and tout is None
    return tin, tout, cache, missing


def normalize_deepseek_usage(usage: dict | None):
    """DeepSeek-shaped usage -> (tokens_in, tokens_out, tokens_cache, missing).

    DeepSeek returns prompt_cache_hit_tokens / prompt_cache_miss_tokens; the HIT
    count is the cached-read count (maps to tokens_cache). prompt_tokens already
    INCLUDES hit+miss, so tokens_in is left as prompt_tokens (not double-counted).
    """
    if not isinstance(usage, dict):
        return None, None, None, True
    tin = usage.get("prompt_tokens", usage.get("input_tokens"))
    tout = usage.get("completion_tokens", usage.get("output_tokens"))
    cache = usage.get("prompt_cache_hit_tokens")
    if cache is None:
        details = usage.get("prompt_tokens_details") or {}
        if isinstance(details, dict):
            cache = details.get("cached_tokens")
    missing = tin is None and tout is None
    return tin, tout, cache, missing


def append_usage(project_path: str, *, provider: str, caller: str, model: str,
                 tokens_in=None, tokens_out=None, tokens_cache=None,
                 meta: dict | None = None, usage_missing: bool = False,
                 ts: str | None = None) -> str | None:
    """Append one usage record to projects/<p>/llm-usage.jsonl.

    Never raises into the caller's hot path — a ledger write must not sink a real
    LLM result. Returns the file path on success, None on failure (warns to stderr).
    """
    try:
        path = ledger_path(project_path)
    except Exception as e:  # noqa: BLE001
        print(f"[llm_usage] no project path — usage NOT recorded ({e})", file=sys.stderr)
        return None
    line = {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "caller": caller,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_cache": tokens_cache,
    }
    if meta:
        line["meta"] = meta
    if usage_missing:
        line["usage_missing"] = True
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return path
    except Exception as e:  # noqa: BLE001
        print(f"[llm_usage] append failed ({path}): {e}", file=sys.stderr)
        return None


# ── summary ───────────────────────────────────────────────────────

def _blank_agg() -> dict:
    return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "tokens_cache": 0,
            "usage_missing": 0}


def read_ledger(project_path: str) -> list[dict]:
    """Read all records; skip blank/corrupt lines gracefully. [] if absent."""
    path = ledger_path(project_path)
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except Exception:  # noqa: BLE001
                continue  # a partial/torn append line — ignore, keep counting rest
    return out


def summarize(records: list[dict]) -> dict:
    """Per-provider aggregate + grand total. Nulls count as 0 tokens but the call
    still counts (that is the ledger's promise)."""
    providers: dict[str, dict] = {}
    grand = _blank_agg()
    for r in records:
        prov = r.get("provider") or "unknown"
        agg = providers.setdefault(prov, _blank_agg())
        for tgt in (agg, grand):
            tgt["calls"] += 1
            tgt["tokens_in"] += r.get("tokens_in") or 0
            tgt["tokens_out"] += r.get("tokens_out") or 0
            tgt["tokens_cache"] += r.get("tokens_cache") or 0
            if r.get("usage_missing"):
                tgt["usage_missing"] += 1
    return {"providers": providers, "total": grand}


def engine_cost_records(costs_dir: str) -> list[dict]:
    """Turn each engine cost report (migration-orchestrator/costs/run_*.json) into
    one synthetic ledger-shaped record under the ENGINE_PROVIDER_LABEL provider.

    The engine's run reports do not carry a project (routing per-project would
    require editing the off-limits orchestrator.py), so these are repo-scoped and
    merged for an honest grand total, not attributed to a single project's file.
    """
    recs = []
    for fp in sorted(glob.glob(os.path.join(costs_dir, "run_*.json"))):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        tot = d.get("total") or {}
        recs.append({
            "provider": ENGINE_PROVIDER_LABEL,
            "caller": f"opencode:{d.get('run_id', os.path.basename(fp))}",
            "model": d.get("model"),
            "tokens_in": tot.get("tokens_in"),
            "tokens_out": tot.get("tokens_out"),
            "tokens_cache": tot.get("tokens_cache"),
        })
    return recs


def _fmt(summary: dict) -> str:
    lines = []
    provs = summary["providers"]
    if not provs:
        lines.append("(no LLM calls recorded)")
    for prov in sorted(provs):
        a = provs[prov]
        lines.append(f"{prov}:")
        lines.append(f"  calls:        {a['calls']:>12,}")
        lines.append(f"  tokens_in:    {a['tokens_in']:>12,}")
        lines.append(f"  tokens_out:   {a['tokens_out']:>12,}")
        lines.append(f"  tokens_cache: {a['tokens_cache']:>12,}")
        if a["usage_missing"]:
            lines.append(f"  usage_missing: {a['usage_missing']} call(s) had no usage block")
    t = summary["total"]
    lines.append("─────────────────────────")
    lines.append("GRAND TOTAL:")
    lines.append(f"  calls:        {t['calls']:>12,}")
    lines.append(f"  tokens_in:    {t['tokens_in']:>12,}")
    lines.append(f"  tokens_out:   {t['tokens_out']:>12,}")
    lines.append(f"  tokens_cache: {t['tokens_cache']:>12,}")
    return "\n".join(lines)


def _repo_costs_dir() -> str:
    # orchestration/lib/llm_usage.py -> repo root -> migration-orchestrator/costs
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    return os.path.join(repo, "migration-orchestrator", "costs")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Summarize a project's LLM usage ledger.")
    ap.add_argument("project", help="projects/<name> (or a bare project name)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--no-engine-costs", action="store_true",
                    help="do NOT merge migration-orchestrator/costs/run_*.json")
    ap.add_argument("--costs-dir", default=None,
                    help="override the engine costs directory")
    args = ap.parse_args(argv)

    records = read_ledger(args.project)
    if not args.no_engine_costs:
        costs_dir = args.costs_dir or _repo_costs_dir()
        records = records + engine_cost_records(costs_dir)

    summary = summarize(records)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"LLM usage — {ledger_path(args.project)}")
        print(_fmt(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
