#!/usr/bin/env python3
"""semantic-idempotent.py — re-deriving the content model must not change it.

semanticize_content transformed the extract payload IN PLACE, so a second pass
consumed its own output. Measured on salonphoto, the same file twice in a row:

    pass 1 (raw extract):    207 semantic, 16 passthrough, 89 images lifted
    pass 2 (its own output): 182 semantic, 41 passthrough,  3 images lifted

25 instances demoted to raw HTML and image lifting all but eliminated — with both
passes reporting success and every other gate still green. The engine retries a
step up to three times by design, so any retry of step_content_extract published
the degraded model, and a retry's "182/41" is indistinguishable from a producer
bug. It cost three false diagnoses in one session before the double pass itself
was measured.

The producer now keeps the extract output beside the payload and re-derives from
it. This gate holds that property: run the transform again into a TEMP file (never
touching the live artifact) and compare the model it yields — instance count,
semantic/passthrough split, and per-nodeType distribution. Any drift fails.

Cheap to satisfy honestly, impossible to satisfy by accident: only a transform
that is a pure function of the extract passes twice.

Usage: semantic-idempotent.py <project> [--manifest PATH]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "lib")


def model_of(payload):
    """The comparable shape of a payload: what the loader would create."""
    types = Counter()
    n_pass = [0]

    def walk(x):
        if isinstance(x, dict):
            nt = x.get("nodeType")
            if isinstance(nt, str) and nt:
                types[nt] += 1
            elif x.get("passthrough"):
                n_pass[0] += 1
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(payload.get("pages") or {})
    return {"types": dict(types), "passthrough": n_pass[0],
            "instances": sum(types.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--manifest", default="")
    a = ap.parse_args()
    p = a.project
    live_p = f"orchestration/content/{p}.content-load.json"
    man = a.manifest or f"projects/{p}/workflow-output/component-manifest.json"
    if not os.path.exists(live_p):
        print(f"PASS semantic-idempotent: no payload at {live_p} — nothing to check")
        return
    live = json.load(open(live_p))
    if live.get("model") != "archetype":
        print("PASS semantic-idempotent: payload is not semanticized yet — the "
              "transform has not run")
        return

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "again.json")
        r = subprocess.run(
            [sys.executable, os.path.join(LIB, "semanticize_content.py"), p,
             "--manifest", man, "--out", out],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            print(f"FAIL semantic-idempotent: re-deriving the model failed "
                  f"(exit {r.returncode})")
            print("  " + (r.stderr or r.stdout or "").strip().replace("\n", "\n  ")[:600])
            sys.exit(1)
        again = json.load(open(out))

    a_m, b_m = model_of(live), model_of(again)
    if a_m == b_m:
        print(f"PASS semantic-idempotent: re-deriving yields the same model "
              f"({a_m['instances']} instance(s), {a_m['passthrough']} passthrough, "
              f"{len(a_m['types'])} type(s))")
        return

    print(f"FAIL semantic-idempotent [{p}] — re-deriving the model CHANGES it, so a "
          f"step retry would publish something different from what was reviewed")
    print(f"  instances   live={a_m['instances']:<6} re-derived={b_m['instances']}")
    print(f"  passthrough live={a_m['passthrough']:<6} re-derived={b_m['passthrough']}")
    for t in sorted(set(a_m["types"]) | set(b_m["types"])):
        x, y = a_m["types"].get(t, 0), b_m["types"].get(t, 0)
        if x != y:
            print(f"  {t:<26} live={x:<6} re-derived={y}")
    print("  Fix: the transform must be a pure function of the extract output — keep "
          "the extract beside the payload and always re-derive from it, never from the "
          "payload it just wrote.")
    sys.exit(1)


if __name__ == "__main__":
    main()
