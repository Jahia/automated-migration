#!/usr/bin/env python3
"""run_local.py — Deterministic plan executor (the orchestrator's contract, no agent).

The migration-orchestrator proves a step done ONLY when every `PROBE:` command in
its acceptance_criteria exits 0. This executor implements exactly that contract
directly: it flattens a plan's steps in dependency order and, for each step, runs
its `Run:` commands then its `PROBE:` commands — a step passes iff all exit 0. No
opencode/agent layer, so execution is fully deterministic; the only LLM is inside
a step's own command (group_llm.py -> DeepSeek), which is itself gate-verified.

Consumes the SAME plan JSON the FastAPI engine consumes (epics/stories/steps with
acceptance_criteria), so a plan authored here also runs under the full engine.

Usage:
  python3 orchestration/run_local.py <plan.json> [--from <step_id>] [--only <step_id>] [--dry]
"""
import argparse
import json
import re
import subprocess
import sys
import time


def flatten_steps(plan):
    steps = []
    for epic in plan.get("epics", []):
        for story in epic.get("stories", []):
            for step in story.get("steps", []):
                steps.append(step)
    return steps


def order_by_deps(steps):
    by_id = {s["id"]: s for s in steps}
    done, ordered = set(), []
    remaining = list(steps)
    guard = 0
    while remaining and guard < 10000:
        guard += 1
        progressed = False
        for s in list(remaining):
            deps = [d for d in s.get("depends_on", []) if d in by_id]
            if all(d in done for d in deps):
                ordered.append(s)
                done.add(s["id"])
                remaining.remove(s)
                progressed = True
        if not progressed:            # cycle or external dep — append rest in order
            ordered.extend(remaining)
            break
    return ordered


def extract(prefix, criteria):
    out = []
    for c in criteria or []:
        m = re.match(rf"\s*{prefix}:\s*(.+)$", c)
        if m:
            out.append(m.group(1).strip())
    return out


def run_cmd(cmd, dry):
    print(f"    $ {cmd}")
    if dry:
        return 0
    t = time.time()
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    dt = time.time() - t
    tail = (r.stdout + r.stderr).strip().splitlines()
    for line in tail[-4:]:
        print(f"      | {line}")
    print(f"      ({r.returncode}, {dt:.1f}s)")
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--only")
    ap.add_argument("--halt-after", dest="halt_after",
                    help="stop after this step for human review (HALT gate); resume with --from <next>")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    plan = json.load(open(args.plan))
    steps = order_by_deps(flatten_steps(plan))
    if args.only:
        steps = [s for s in steps if s["id"] == args.only]
    elif args.start:
        idx = next((i for i, s in enumerate(steps) if s["id"] == args.start), 0)
        steps = steps[idx:]

    print(f"=== run_local: {plan.get('goal','plan')[:70]} ===")
    print(f"steps: {[s['id'] for s in steps]}\n")

    results = []
    for s in steps:
        crit = s.get("acceptance_criteria", [])
        runs = extract("Run", crit)
        probes = extract("PROBE", crit)
        print(f"── STEP {s['id']}: {s.get('title','')}")
        ok = True
        for cmd in runs:
            if run_cmd(cmd, args.dry) != 0:
                ok = False
                print(f"    RUN FAILED — step {s['id']} incomplete")
                break
        if ok:
            for cmd in probes:
                if run_cmd(cmd, args.dry) != 0:
                    ok = False
                    print(f"    PROBE FAILED — step {s['id']} NOT proven")
                    break
        status = "DONE" if ok else "FAILED"
        results.append((s["id"], status))
        print(f"  => {s['id']}: {status}\n")
        if not ok:
            break
        if args.halt_after and s["id"] == args.halt_after:
            nxt = steps[steps.index(s) + 1]["id"] if steps.index(s) + 1 < len(steps) else None
            print(f"  ⏸  HALT after {s['id']} — human review gate.")
            print(f"     Inspect the output, then resume with:  --from {nxt}" if nxt else "     (last step)")
            break

    print("=== SUMMARY ===")
    for sid, st in results:
        print(f"  {sid:24s} {st}")
    failed = [r for r in results if r[1] != "DONE"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
