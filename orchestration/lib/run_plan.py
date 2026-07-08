#!/usr/bin/env python3
"""run_plan.py — generic sequential plan executor (P3).

Executes a gen_plan.py plan directly: every `Run:` line then every `PROBE:`
line of each step, in dependency order (the plans are linear), stopping at the
FIRST failure. `Gate: ... halt.` lines are logged (the operator reviews the
artifacts). PROBE[NNN] carries its own timeout. Env comes from .env.local
loaded with export (set -a) — plain `source` does not export.

Usage: run_plan.py <plan.json> [--from step_id] [--until step_id] [--skip id,id]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

PROBE_RE = re.compile(r"^PROBE(\[(\d+)\])?:\s*(.+)$")


def sh(cmd, timeout, extra_env=None):
    # NO blanket env export: probes self-load (.sh via load_env, python via
    # mcp_client's .env parsing) and jahia-deploy's dotenv DOES NOT OVERRIDE
    # already-exported vars — exporting .env.local here poisoned it with a
    # passwordless JAHIA_USER (observed live: guest 401 on provisioning).
    # extra_env is ONLY the provenance pair (ORCH_RUN_ID/ORCH_STEP_ID) — the
    # no-.env.local doctrine above stands untouched.
    full = cmd
    env = None
    if extra_env:
        env = dict(os.environ)
        env.update(extra_env)
    t0 = time.time()
    r = subprocess.run(["bash", "-c", full], capture_output=True, text=True,
                       timeout=timeout, env=env)
    dt = time.time() - t0
    return r.returncode, (r.stdout + r.stderr)[-2000:], dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--from", dest="from_", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--skip", default="")
    a = ap.parse_args()
    skip = set(x for x in a.skip.split(",") if x)
    plan = json.load(open(a.plan))
    steps = [st for e in plan["epics"] for s in e["stories"] for st in s["steps"]]
    # provenance: every child tool stamps its artifacts with this run/step id
    # (orchestration/lib/provenance.py|.mjs read them from the environment).
    run_id = f"local_{int(time.time() * 1000)}"
    started = a.from_ is None
    for st in steps:
        sid = st["id"]
        if not started:
            if sid == a.from_:
                started = True
            else:
                print(f"~~ {sid} (skipped: before --from)")
                continue
        if sid in skip:
            print(f"~~ {sid} (skipped: --skip)")
            continue
        print(f"== {sid}: {st['title']}", flush=True)
        for line in st["acceptance_criteria"]:
            line = line.strip()
            if line.startswith("Run:"):
                cmd, timeout = line[4:].strip(), 1800
            else:
                m = PROBE_RE.match(line)
                if not m:
                    print(f"   (gate) {line[:100]}")
                    continue
                cmd, timeout = m.group(3), int(m.group(2) or 300)
            try:
                code, out, dt = sh(cmd, timeout,
                                   {"ORCH_RUN_ID": run_id, "ORCH_STEP_ID": sid})
            except subprocess.TimeoutExpired:
                print(f"   ✗ TIMEOUT({timeout}s): {cmd[:120]}")
                sys.exit(1)
            tail = "\n".join(out.strip().splitlines()[-3:])
            print(f"   {'✓' if code == 0 else '✗'} [{dt:5.1f}s] {cmd[:110]}")
            if code != 0:
                print(f"--- output tail ---\n{tail}")
                print(f"FAILED at {sid}")
                sys.exit(1)
        if a.until and sid == a.until:
            print(f"(stopping after --until {sid})")
            break
    print("PLAN COMPLETE")


if __name__ == "__main__":
    main()
