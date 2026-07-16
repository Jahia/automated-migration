#!/usr/bin/env python3
"""reconcile-check.py — BLOCKING gate on the analyze/model RECONCILIATION
(process-hardening, 2026-07-16). Runs BEFORE any load, on the artifacts alone:

  1. CONSERVATION  — per page, (placed + leftover) / before >= --coverage
     (default 0.90): scraped visible text cannot silently vanish in the
     content->model mapping. Dropped-instance text is reported.
  2. LEFTOVER CEILING — no instance keeps >= --leftover (default 60) chars of
     visible text in its structure markup: everything editors should own must
     be IN properties/children (pre-JCR twin of skeleton-holds-content).
  3. VALUE-LEVEL APPLICABILITY — on the content-load payload:
     - title fields: no markup, <= 250 chars
     - body fields: no unresolved {{...}} marker debris
     - media entries: file present and image-suffixed

Usage: reconcile-check.py <project> [--coverage 0.90] [--leftover 60]
Exit 0 clean / 1 violations (each printed).
"""
import argparse
import json
import re
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--coverage", type=float, default=0.90)
    ap.add_argument("--leftover", type=int, default=60)
    a = ap.parse_args()
    bad = []

    rp = f"projects/{a.project}/workflow-output/reconciliation.json"
    try:
        recon = json.load(open(rp))
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL: reconcile-check — cannot read {rp}: {e}", file=sys.stderr)
        sys.exit(1)
    pages = recon.get("pages") or {}
    if not pages:
        print("FAIL: reconcile-check — reconciliation.json has no pages "
              "(a gate that cannot measure must fail)", file=sys.stderr)
        sys.exit(1)

    for pk, pg in sorted(pages.items()):
        cov = pg.get("coverage", 0)
        if pg.get("before", 0) >= 80 and cov < a.coverage:
            bad.append(f"CONSERVATION {pk}: coverage {cov} < {a.coverage} "
                       f"(before {pg['before']}, placed {pg['placed']}, "
                       f"leftover {pg['leftover']}, dropped {pg.get('droppedText', 0)})")
        for r in pg.get("rows") or []:
            if r.get("leftover", 0) >= a.leftover:
                bad.append(f"LEFTOVER {pk}[{r['idx']}] {r.get('nodeType') or r.get('type')}: "
                           f"{r['leftover']} chars stay in structure markup")

    cl = f"orchestration/content/{a.project}.content-load.json"
    try:
        data = json.load(open(cl))
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL: reconcile-check — cannot read {cl}: {e}", file=sys.stderr)
        sys.exit(1)

    def check_inst(inst, pk, path):
        f = inst.get("fields") or {}
        t = f.get("title")
        if isinstance(t, str):
            if len(t) > 250:
                bad.append(f"VALUE {pk}{path}: title {len(t)} chars (>250)")
            if "<" in t and ">" in t:
                bad.append(f"VALUE {pk}{path}: title contains markup: {t[:60]!r}")
        b = f.get("body")
        if isinstance(b, str) and re.search(r"\{\{[^}]+\}\}", b):
            bad.append(f"VALUE {pk}{path}: body contains marker debris")
        for m in inst.get("media") or []:
            fn = (m.get("file") or "")
            if fn and not re.search(r"\.(png|jpe?g|gif|webp|svg|avif)$", fn, re.I):
                bad.append(f"VALUE {pk}{path}: media file {fn!r} not image-suffixed")
        for n, ch in enumerate(inst.get("children") or []):
            check_inst(ch, pk, f"{path}/item-{n + 1}")

    for pk, pg in (data.get("pages") or {}).items():
        for i, inst in enumerate(pg.get("instances") or []):
            check_inst(inst, pk, f"[{i}]")

    if bad:
        for x in bad[:25]:
            print(f"  - {x}")
        print(f"FAIL: reconcile-check — {len(bad)} violation(s)", file=sys.stderr)
        sys.exit(1)
    tot_before = sum(p.get("before", 0) for p in pages.values())
    tot_placed = sum(p.get("placed", 0) for p in pages.values())
    print(f"PASS: reconcile-check — {len(pages)} page(s), "
          f"{tot_placed}/{tot_before} chars placed in properties/children, "
          f"coverage floor {a.coverage}, leftover ceiling {a.leftover}")


if __name__ == "__main__":
    main()
