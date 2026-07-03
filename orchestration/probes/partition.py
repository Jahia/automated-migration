#!/usr/bin/env python3
"""partition.py — the P1.2 HARD partition gate (QUALITY-PLAN §5 P1.2).

The fidelity invariant (§2) holds only if every content leaf of every page's
<main> region is covered EXACTLY ONCE — by a semantic component instance or by
an explicit rawHtml passthrough instance. A page silently dropping content must
fail here, before anything is deployed or loaded.

Checks, per semantic-adapter page of orchestration/content/<project>.content-load.json:
  total     — partition.leavesCovered == partition.leavesTotal (nothing dropped)
  payload   — #passthrough instances in the payload == partition.passthroughRegions
              (the summary matches what the loader will actually create)
  nonempty  — a page whose <main> has content leaves has >= 1 region
Reports the semantic leaf share (quality dial — measured, no floor in P1).

Usage: partition.py <project> [--min-semantic-share PCT]
Exit 0 only if the partition is total on every page (and the share floor, if
given, is met — P2 sets one; P1 measures only).
"""
import json
import sys

if len(sys.argv) < 2:
    sys.exit("usage: partition.py <project> [--min-semantic-share PCT]")
PROJECT = sys.argv[1]
floor = None
if "--min-semantic-share" in sys.argv:
    floor = float(sys.argv[sys.argv.index("--min-semantic-share") + 1]) / 100.0

path = f"orchestration/content/{PROJECT}.content-load.json"
try:
    data = json.load(open(path))
except Exception as e:
    sys.exit(f"FAIL: cannot read {path}: {e}")

fails, shares = [], []
sem_pages = 0
for slug, pg in sorted(data.get("pages", {}).items()):
    if pg.get("adapter") != "semantic":
        continue
    sem_pages += 1
    part = pg.get("partition")
    if not part:
        fails.append(f"{slug}: no partition block (pre-P1.2 payload — re-run extract_content)")
        continue
    total, covered = part.get("leavesTotal", 0), part.get("leavesCovered", 0)
    if covered != total:
        fails.append(f"{slug}: partition NOT total — {covered}/{total} leaves covered")
    # area-flagged chrome is not a main-region payload (installed once per site)
    n_pass_payload = sum(1 for i in pg.get("instances", [])
                         if i.get("passthrough") and not i.get("area"))
    if n_pass_payload != part.get("passthroughRegions", 0):
        fails.append(f"{slug}: payload/summary mismatch — {n_pass_payload} passthrough "
                     f"instances vs {part.get('passthroughRegions')} regions")
    if total > 0 and part.get("componentRegions", 0) + part.get("passthroughRegions", 0) == 0:
        fails.append(f"{slug}: {total} content leaves but zero regions")
    if part.get("semanticLeafShare") is not None:
        shares.append((part["semanticLeafShare"], slug))

if sem_pages == 0:
    sys.exit(f"FAIL: no semantic-adapter pages in {path} (nothing to gate)")

print(f"partition gate: {sem_pages} semantic page(s)")
if shares:
    shares.sort()
    avg = sum(s for s, _ in shares) / len(shares)
    print(f"  semantic leaf share: min={shares[0][0]:.0%} ({shares[0][1]}) "
          f"avg={avg:.0%} max={shares[-1][0]:.0%}")
    if floor is not None:
        below = [(s, sl) for s, sl in shares if s < floor]
        for s, sl in below:
            fails.append(f"{sl}: semantic share {s:.0%} < floor {floor:.0%}")

if fails:
    print(f"FAIL — {len(fails)} problem(s):")
    for f in fails:
        print(f"  ✗ {f}")
    sys.exit(1)
print("PASS — partition total on every page (nothing dropped)")
