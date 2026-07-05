"""LLM usage accounting bridge (P5.5).

Every direct-API response carries a `usage` block. This module routes it to the
TWO accounting sinks the repo already has, unchanged in format:

  1. The step's token counters (tokens_in/out/cache on StepState) — these are what
     the orchestrator's run-end `finally` block feeds into cost_tracker.write_run_cost
     (migration-orchestrator/costs/run_*.json). We ACCUMULATE (+=) because a repair
     step makes many chat() calls; the run cost report sums per step.

  2. The centralized per-project ledger (orchestration/lib/llm_usage.py):
     append-only JSONL at projects/<p>/llm-usage.jsonl, one line per LLM call,
     provider="deepseek-direct". This is Julian's standing "account for every call"
     requirement. A call is logged even when usage is absent (nulls +
     usage_missing:true) so the CALL COUNT is always exact.

Neither sink is allowed to raise into the caller's hot path — accounting must
never sink a real LLM result.
"""
from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger(__name__)

# The per-project ledger lives in orchestration/lib (shared JS/Python contract).
# Import it lazily-but-once; add the repo lib dir to sys.path if needed. Guarded
# so a missing/renamed ledger never crashes the engine — it degrades to "step
# counters only" with a warning.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LIB_DIR = os.path.join(_REPO_ROOT, "orchestration", "lib")

PROVIDER = "deepseek-direct"


def _import_ledger():
    try:
        if _LIB_DIR not in sys.path:
            sys.path.insert(0, _LIB_DIR)
        import llm_usage  # type: ignore  # noqa: PLC0415

        return llm_usage
    except Exception as e:  # noqa: BLE001
        log.warning(f"llm_usage ledger unavailable ({e}); per-project ledger disabled this call")
        return None


def normalize_usage(usage: dict | None) -> tuple[int, int, int, bool]:
    """OpenAI/DeepSeek-shaped usage → (tokens_in, tokens_out, tokens_cache, missing).
    Delegates to the shared ledger's normaliser (maps DeepSeek
    prompt_cache_hit_tokens → cache) when available, with a self-contained
    fallback so token accounting works even if the ledger import failed."""
    mod = _import_ledger()
    if mod is not None:
        try:
            tin, tout, cache, missing = mod.normalize_deepseek_usage(usage)
            return (tin or 0, tout or 0, cache or 0, bool(missing))
        except Exception:  # noqa: BLE001
            pass
    if not isinstance(usage, dict):
        return 0, 0, 0, True
    tin = usage.get("prompt_tokens", usage.get("input_tokens"))
    tout = usage.get("completion_tokens", usage.get("output_tokens"))
    cache = usage.get("prompt_cache_hit_tokens")
    if cache is None:
        details = usage.get("prompt_tokens_details") or {}
        cache = details.get("cached_tokens") if isinstance(details, dict) else None
    missing = tin is None and tout is None
    return (tin or 0, tout or 0, cache or 0, bool(missing))


def project_of(run, step=None) -> str | None:
    """Resolve the ledger's project pointer for a run/step. The step's
    inputs.project (a bare name like "sial-paris" or a "projects/<name>" path)
    is authoritative; ledger_path() normalises a bare name under projects/. None
    when no project is derivable (ledger append is then skipped, not fatal)."""
    if step is not None:
        proj = (step.inputs or {}).get("project")
        if proj:
            return str(proj)
    # No per-step project → try any step in the run that carries one.
    try:
        for epic in run.epics:
            for story in epic.stories:
                for st in story.steps:
                    proj = (st.inputs or {}).get("project")
                    if proj:
                        return str(proj)
    except Exception:  # noqa: BLE001
        pass
    return None


def record(run, step, usage: dict | None, *, caller: str, model: str) -> None:
    """Route ONE chat() response's usage to both sinks. Never raises.

    - step counters: ACCUMULATE tokens_in/out/cache (run-end cost report sums per step);
    - project ledger: append one line (provider=deepseek-direct), always counting
      the call even when usage is missing.
    """
    tin, tout, cache, missing = normalize_usage(usage)

    # 1. step counters (feed cost_tracker at run end)
    try:
        if step is not None:
            step.tokens_in += tin
            step.tokens_out += tout
            step.tokens_cache += cache
    except Exception as e:  # noqa: BLE001
        log.warning(f"failed to accumulate step token counters: {e}")

    # 2. per-project ledger
    project = project_of(run, step)
    if not project:
        return
    mod = _import_ledger()
    if mod is None:
        return
    try:
        mod.append_usage(
            project,
            provider=PROVIDER,
            caller=caller,
            model=model,
            tokens_in=(tin if not missing else None),
            tokens_out=(tout if not missing else None),
            tokens_cache=(cache if not missing else None),
            meta={"run_id": getattr(run, "run_id", None), "step_id": getattr(step, "id", None)},
            usage_missing=missing,
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"failed to append per-project LLM ledger line: {e}")
