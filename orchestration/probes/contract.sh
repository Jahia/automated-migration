#!/usr/bin/env bash
# contract.sh — INTER-STEP DATA CONTRACT gate.
#
# The orchestration loop passes almost nothing between steps in the prompt (only
# a truncated summary + filenames from prior approved stories in the SAME epic;
# `depends_on` is ordering-only and never injected; `expected_outputs` is shown
# to the agent but never verified). The real hand-off is FILES ON DISK. When a
# consumer reads a missing artifact it does NOT error — e.g. load_content.py
# falls back to {} and creates ZERO content. This gate makes the file contract
# executable so "is the passed data sufficient?" is verified, not hoped:
#
#   * produces — every file this step must WRITE exists and is non-empty/non-stub
#   * consumes — every file this step READS exists at its canonical path (else the
#                upstream producer silently failed to deliver — named in the error)
#
# The contract table lives in orchestration/lib/contract.py (single source of
# truth). This check is ungameable: it inspects the real artifact at the real
# path the consumer reads, not a proxy threshold.
#
# Usage: contract.sh <project_path> <step_id>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
step="${2:?step_id required}"
project="$(basename "$proj")"
root="$(cd "$HERE/../.." && pwd)"
cd "$root"

python3 - "$project" "$step" <<'PY'
import json, os, sys
sys.path.insert(0, "orchestration/lib")
import contract  # single source of truth

project, step = sys.argv[1], sys.argv[2]
spec = contract.for_step(step, project)
produces, consumes = spec["produces"], spec["consumes"]

if not produces and not consumes:
    print(f"contract[{step}]: no cross-step artifacts declared — nothing to enforce")
    sys.exit(0)

def nonstub(path: str) -> str | None:
    """Return an error string if the artifact is missing/empty/stub, else None."""
    if not os.path.exists(path):
        return "missing"
    size = os.path.getsize(path)
    if size <= 2:                       # "", "{}", "[]"
        return f"empty ({size}b)"
    if path.endswith(".json"):
        try:
            data = json.load(open(path))
        except Exception as e:
            return f"unreadable JSON: {e}"
        # a hand-off JSON with no keys/items is a stub the consumer treats as {}
        if isinstance(data, dict) and not data:
            return "empty object {} (consumer would read no data)"
        if isinstance(data, list) and not data:
            return "empty array []"
        # pages-shaped manifests must actually cover pages
        if isinstance(data, dict) and "pages" in data and not data["pages"]:
            return "'pages' is empty (no per-page content/media)"
    return None

errors = []

# post-condition: outputs this step must have produced
for p in produces:
    err = nonstub(p)
    if err:
        errors.append(f"OUTPUT not delivered: {p} — {err}")

# pre-condition: inputs this step consumes (produced upstream)
for c in consumes:
    err = nonstub(c)
    if err:
        who = contract.producer_of(
            next((t for t in contract.PRODUCED_BY if t.replace("{project}", project) == c), c)
        )
        errors.append(f"INPUT unavailable: {c} — {err}  (should be produced by {who})")

if errors:
    print(f"\ncontract[{step}] FAILURES:")
    for e in errors:
        print("  ✗", e)
    sys.exit(1)

if produces:
    print(f"contract[{step}]: {len(produces)} output(s) delivered non-empty")
if consumes:
    print(f"contract[{step}]: {len(consumes)} input(s) available at canonical paths")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "contract[$step]: inter-step artifact contract not satisfied (see above) — the data passed to/from this step is insufficient"
pass "contract[$step]: inter-step artifact contract satisfied"
