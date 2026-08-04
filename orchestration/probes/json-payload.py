#!/usr/bin/env python3
"""json-payload.py — a JSON artifact must carry a PAYLOAD, not just braces.

`PROBE: test -s <artifact>.json` asks whether the file has bytes. `{}` is two
bytes, `{"pages": []}` is fifteen, and both sail through — so a step whose
producer silently yielded nothing still reports green, and the emptiness is
discovered several steps later (or after the load, by looking). This is the same
defect class that let an asset registry with `"urlMap": {}` pass step_localize
(2026-08-04) and that made archetype-utilization pass on a payload with zero
instances: **a gate that only checks existence cannot measure content.**

The rule here is deliberately generic so it can replace `test -s` mechanically:
an artifact is hollow when every collection it declares at the top level is
empty. That is producer-agnostic and needs no per-artifact key knowledge, while
still catching the real failure (a producer that wrote its skeleton and no rows).

FAILS when:
  1. the file is missing, empty, or not parseable JSON,
  2. the top level is `{}` / `[]`,
  3. every top-level list/dict value is empty (a skeleton with no rows),
  4. --expect names a key that is absent or empty,
  5. --min N is given and the largest top-level collection holds < N items.

Usage: json-payload.py <file.json> [--expect pages,urlMap] [--min 1]
"""
import argparse
import json
import os
import sys


def size(v):
    return len(v) if isinstance(v, (list, dict, str)) else (1 if v not in (None, 0, False) else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--expect", default="", help="comma-separated keys that must be non-empty")
    ap.add_argument("--min", type=int, default=1, help="largest collection must hold >= N")
    a = ap.parse_args()

    if not os.path.exists(a.path):
        sys.exit(f"FAIL json-payload: {a.path} does not exist")
    if os.path.getsize(a.path) == 0:
        sys.exit(f"FAIL json-payload: {a.path} is 0 bytes")
    try:
        d = json.load(open(a.path))
    except ValueError as e:
        sys.exit(f"FAIL json-payload: {a.path} is not parseable JSON ({e})")

    fails = []
    if isinstance(d, (dict, list)) and len(d) == 0:
        fails.append(f"top level is an empty {'object' if isinstance(d, dict) else 'array'}")

    if isinstance(d, dict):
        colls = {k: v for k, v in d.items() if isinstance(v, (list, dict))}
        # ignore documentation-only keys: an artifact whose only content is its README
        # is still hollow (_README, _note… are conventions in this harness)
        real = {k: v for k, v in colls.items() if not k.startswith("_")}
        # an artifact whose only non-empty key is its own _README is hollow too: the
        # documentation survived and the content did not (caught by fixture, 2026-08-04)
        if not any(size(v) > 0 for k, v in d.items() if not k.startswith("_")):
            fails.append("no non-empty content key — only documentation ("
                         + ", ".join(k for k in d if k.startswith("_"))[:60]
                         + ") and/or empty values survived")
        biggest = max((size(v) for v in real.values()), default=0)
        if real and biggest == 0:
            fails.append(f"every collection is EMPTY ({', '.join(sorted(real))}) — the "
                         f"producer wrote its skeleton and no rows")
        elif real and biggest < a.min:
            fails.append(f"largest collection holds {biggest} item(s), need >= {a.min}")
        for k in [x.strip() for x in a.expect.split(",") if x.strip()]:
            if k not in d:
                fails.append(f"expected key '{k}' is absent")
            elif size(d[k]) == 0:
                fails.append(f"expected key '{k}' is empty")
    elif isinstance(d, list) and len(d) < a.min:
        fails.append(f"array holds {len(d)} item(s), need >= {a.min}")

    if fails:
        print(f"FAIL json-payload [{a.path}]")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)

    if isinstance(d, dict):
        shape = ", ".join(f"{k}={size(v)}" for k, v in list(d.items())[:5]
                          if isinstance(v, (list, dict)) and not k.startswith("_"))
    else:
        shape = f"{len(d)} item(s)"
    print(f"PASS json-payload: {os.path.basename(a.path)} carries a payload ({shape})")


if __name__ == "__main__":
    main()
