#!/usr/bin/env python3
"""plan-lint.py — check a plan BEFORE the orchestrator burns a run on it.

A plan is a contract the engine executes verbatim, so a plan-level mistake costs a
whole run and looks like a mysterious step failure with no probe output. Measured
example: gen_plan defaulted `repo_dir` to `"."`. The engine resolves every probe's
cwd from repo_dir, `"."` resolved against the ORCHESTRATOR's cwd, so step_connect
reported `engine_executed commands=0` and then `failed` — three attempts, then
`decision_pending: retries_exhausted` — while the same probe passed by hand
(salonphoto run_1785743247256, 2026-08-03).

Checks:
  1. repo_dir is ABSOLUTE, exists, and is a harness root (AGENTS.md + orchestration/probes).
  2. every referenced `orchestration/...` script in a Run:/PROBE: line EXISTS
     (a typo'd or not-yet-written probe is a guaranteed dead run).
  3. every non-review step carries a PROBE: line OR an explicit `Gate:` line — a
     step that neither proves anything nor declares a human/advisory gate is a
     silent no-op. (Under the archetype model some pixel probes are deliberately
     demoted to advisory `Run: … || true` and pair with a `Gate:` line; that is a
     recorded decision, not an omission.)
  4. review steps carry NO PROBE: line (they are decision points by design).
  5. step ids are unique and every depends_on target exists.

Usage: plan-lint.py <plan.json>
"""
import json
import os
import re
import sys

SCRIPT_RE = re.compile(r"(orchestration/[\w./-]+\.(?:py|sh|mjs|js))(?![\w])")


def main():
    path = sys.argv[1]
    try:
        plan = json.load(open(path))
    except (OSError, ValueError) as e:
        sys.exit(f"FAIL plan-lint: cannot read {path} ({e})")

    fails = []
    repo = plan.get("repo_dir") or ""
    if not os.path.isabs(repo):
        fails.append(f"repo_dir {repo!r} is not absolute — the engine resolves probe cwd "
                     f"from it and will execute 0 commands")
    elif not os.path.isdir(repo):
        fails.append(f"repo_dir {repo!r} does not exist")
    else:
        for need in ("AGENTS.md", "orchestration/probes"):
            if not os.path.exists(os.path.join(repo, need)):
                fails.append(f"repo_dir {repo!r} is not a harness root (missing {need})")

    steps = [s for e in plan.get("epics", []) for t in e.get("stories", [])
             for s in t.get("steps", [])]
    if not steps:
        fails.append("plan has no steps")
    ids = [s["id"] for s in steps]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        fails.append(f"duplicate step id(s): {', '.join(dupes)}")
    known = set(ids)
    root = repo if os.path.isdir(repo) else "."
    missing_scripts, no_probe, review_probe, bad_dep = set(), [], [], []
    for s in steps:
        crit = s.get("acceptance_criteria") or []
        probes = [c for c in crit if c.startswith("PROBE")]
        if s.get("review"):
            if probes:
                review_probe.append(s["id"])
        elif not probes and not any(c.startswith("Gate:") for c in crit):
            no_probe.append(s["id"])
        for c in crit:
            for m in SCRIPT_RE.findall(c):
                if not os.path.exists(os.path.join(root, m)):
                    missing_scripts.add(f"{s['id']}: {m}")
        for d in s.get("depends_on") or []:
            if d not in known:
                bad_dep.append(f"{s['id']} -> {d}")
    if missing_scripts:
        fails.append(f"{len(missing_scripts)} referenced script(s) do not exist: "
                     + "; ".join(sorted(missing_scripts)[:6]))
    if no_probe:
        fails.append(f"{len(no_probe)} non-review step(s) neither prove nor declare a "
                     f"gate (no PROBE:, no Gate:): "
                     + ", ".join(no_probe[:6]))
    if review_probe:
        fails.append(f"review step(s) carrying a PROBE (decision points must not gate): "
                     + ", ".join(review_probe))
    if bad_dep:
        fails.append(f"depends_on target(s) not in the plan: {', '.join(bad_dep[:6])}")

    if fails:
        print(f"FAIL plan-lint [{path}]")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    nprobe = sum(1 for s in steps for c in s.get("acceptance_criteria", [])
                 if c.startswith("PROBE"))
    print(f"PASS plan-lint: {len(steps)} step(s), {nprobe} probe(s), repo_dir={repo}, "
          f"all referenced scripts present")


if __name__ == "__main__":
    main()
