#!/usr/bin/env python3
"""wire_contract.py — inject the artifact contract into a migration plan.

Reads the canonical contract table (contract.py) and, for every step present in
a plan, wires three things the loop otherwise never gives the agent:

  1. expected_outputs   — the files the step must produce (renders into the agent
                          prompt as "SORTIES ATTENDUES", so the agent is TOLD what
                          to write and where).
  2. inputs.consumes    — the canonical paths of the artifacts the step reads
                          (so the agent is TOLD where to read, instead of guessing
                          a path from the skill and silently missing it).
  3. a contract.sh PROBE — appended to acceptance_criteria so the loop's verifier
                          actually enforces 1+2 (the verifier only runs PROBE:
                          lines; expected_outputs alone is never checked).

Placeholders: plan templates use {project} literally? No — plans use __PROJECT__
before instantiation and a real slug after. We substitute using the plan's own
project value when concrete, else leave {project} for the template.

Idempotent: re-running replaces the wired fields rather than duplicating them.

Usage:
  python3 orchestration/lib/wire_contract.py orchestration/plans/<plan>.json [--check]
  python3 orchestration/lib/wire_contract.py orchestration/plan-template.json
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, "orchestration/lib")
import contract  # noqa: E402

PROBE_PREFIX = "PROBE: bash orchestration/probes/contract.sh"


def project_token(plan: dict) -> str:
    """The token to embed in paths: the concrete slug, or a template placeholder."""
    goal = plan.get("goal", "") + json.dumps(plan.get("epics", []))[:200]
    # template files carry __PROJECT__; instantiated plans carry a real slug in repo_dir
    m = re.search(r"projects/([A-Za-z0-9_-]+)", json.dumps(plan))
    if "__PROJECT__" in json.dumps(plan):
        return "__PROJECT__"
    return m.group(1) if m else "{project}"


def contract_paths(step_id: str, token: str) -> dict:
    spec = contract.CONTRACT.get(step_id)
    if spec is None:
        return {"produces": [], "consumes": []}
    return {
        "produces": [p.replace("{project}", token) for p in spec.get("produces", [])],
        "consumes": [p.replace("{project}", token) for p in spec.get("consumes", [])],
    }


def wire_step(step: dict, token: str, project_path: str) -> list[str]:
    """Wire one step in place. Returns a list of human-readable changes."""
    sid = step.get("id", "")
    spec = contract_paths(sid, token)
    produces, consumes = spec["produces"], spec["consumes"]
    if not produces and not consumes:
        return []
    changes = []

    # 1. expected_outputs
    if produces:
        want = {f"artifact_{i}": p for i, p in enumerate(produces)}
        if step.get("expected_outputs") != want:
            step["expected_outputs"] = want
            changes.append(f"expected_outputs={len(produces)} file(s)")

    # 2. inputs.consumes (list of canonical read paths)
    if consumes:
        step.setdefault("inputs", {})
        if step["inputs"].get("consumes") != consumes:
            step["inputs"]["consumes"] = consumes
            changes.append(f"inputs.consumes={len(consumes)} path(s)")

    # 3. contract.sh PROBE in acceptance_criteria (idempotent)
    ac = step.setdefault("acceptance_criteria", [])
    probe_line = f"{PROBE_PREFIX} {project_path} {sid}"
    ac[:] = [c for c in ac if PROBE_PREFIX not in c]  # drop any stale one
    ac.append(probe_line)
    changes.append("contract.sh PROBE")
    return changes


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    check = "--check" in sys.argv[2:]
    plan = json.load(open(path))

    token = project_token(plan)
    project_path = f"projects/{token}"
    print(f"plan: {path}\nproject token: {token}\n")

    before = json.dumps(plan, sort_keys=True)
    touched = 0
    for epic in plan.get("epics", []):
        for story in epic.get("stories", []):
            for step in story.get("steps", []):
                changes = wire_step(step, token, project_path)
                if changes:
                    touched += 1
                    print(f"  {step.get('id'):22s} → {', '.join(changes)}")
    after = json.dumps(plan, sort_keys=True)

    if check:
        if before != after:
            print(f"\nCHECK FAILED: {path} is not wired (run without --check to fix)")
            return 1
        print(f"\nCHECK OK: {path} already carries the contract on all {touched} steps")
        return 0

    if before == after:
        print(f"\nno change — {path} already wired ({touched} steps carry the contract)")
        return 0

    json.dump(plan, open(path, "w"), indent=2, ensure_ascii=False)
    open(path, "a").write("\n")
    print(f"\nwired {touched} step(s) into {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
