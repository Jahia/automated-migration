#!/usr/bin/env python3
"""provenance.py — shared provenance stamp for every pipeline artifact (P0).

Traces any workflow-output file back to the exact invocation that wrote it.
Record (mirrored by provenance.mjs — keep the two in sync):

  { "run_id":  ORCH_RUN_ID or null   (exported by the plan executors),
    "step_id": ORCH_STEP_ID or null,
    "generated_at": "<ISO-8601 UTC>",
    "git_sha": "<short sha>" + "-dirty" when the worktree has any change,
               null when git is unavailable (never crashes a producer),
    "tool": "<script basename>",
    "args": [argv strings],
    "page_set": [slugs processed by THIS invocation] or null }

Placement contract:
  * JSON dict artifacts embed the record under a top-level "_provenance" key
    (ADDITIVE — existing keys stay untouched, in order; lists/scalars are
    sidecar-only).
  * an artifact DIRECTORY (mirror/, reconstruct/, groundtruth/, segment/,
    zone-overlay/, compose/) gets <dir>/provenance.json describing the LAST
    invocation.
  * a single artifact file X.json gets a sibling X.provenance.json.
Old artifacts without provenance stay valid — no consumer may require it.
"""
import json
import os
import subprocess
import sys
import time

_UNSET = object()
_git_sha_cache = _UNSET  # computed once per process


def _git_sha():
    """Short sha (+"-dirty" if the worktree is dirty); None if git is unusable."""
    global _git_sha_cache
    if _git_sha_cache is not _UNSET:
        return _git_sha_cache
    cwd = os.path.dirname(os.path.abspath(__file__))  # always inside the repo
    try:
        sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, cwd=cwd,
                             timeout=10).stdout.strip()
        if sha:
            st = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, cwd=cwd,
                                timeout=10)
            _git_sha_cache = sha + ("-dirty" if st.stdout.strip() else "")
        else:
            _git_sha_cache = None
    except Exception:  # git absent/broken must never sink a producer
        _git_sha_cache = None
    return _git_sha_cache


def provenance_dict(tool, args=None, page_set=None):
    """The provenance record for THIS invocation (env run/step, cached git sha)."""
    return {
        "run_id": os.environ.get("ORCH_RUN_ID") or None,
        "step_id": os.environ.get("ORCH_STEP_ID") or None,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": _git_sha(),
        "tool": tool,
        "args": list(args) if args is not None else sys.argv[1:],
        "page_set": list(page_set) if page_set is not None else None,
    }


def stamp_json(obj, tool, page_set=None):
    """Embed the record under "_provenance" (dicts only, key appended LAST so
    existing keys keep their order). Non-dicts pass through untouched —
    lists/scalars are sidecar-only per the contract."""
    if isinstance(obj, dict):
        obj["_provenance"] = provenance_dict(tool, page_set=page_set)
    return obj


def write_sidecar(path_or_dir, tool, page_set=None):
    """X.json -> sibling X.provenance.json; a directory -> <dir>/provenance.json
    (the LAST invocation wins). Never raises — provenance must not sink a run."""
    try:
        if os.path.isdir(path_or_dir):
            out = os.path.join(path_or_dir, "provenance.json")
        else:
            base = path_or_dir[:-5] if path_or_dir.endswith(".json") else path_or_dir
            out = base + ".provenance.json"
        with open(out, "w") as f:
            json.dump(provenance_dict(tool, page_set=page_set), f, indent=2)
        return out
    except OSError:
        return None
