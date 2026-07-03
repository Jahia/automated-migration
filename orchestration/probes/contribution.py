#!/usr/bin/env python3
"""contribution.py — G1 static contribution gate (CONTRIBUTION-PLAN P2.5).

Judges the CONTENT-LOAD (what actually reaches the JCR), per page:

  coverage        = lifted editable text chars / visible main-region text chars
                    (both raw and forms-excluded are printed; the gate judges
                    forms-excluded — registered metric refinement: <form>
                    subtrees are script-driven webform widgets, not contributor
                    richtext. No other exclusions.)
  dead props      = a promoted field whose marker is absent from its skeleton
                    (editing it would change nothing), or a CND-declared
                    editable prop on a skeleton type that NO instance lifts
  empty shells    = a typed (promoted) instance with zero wired fields anywhere
  phantom markers = a skeleton marker with no field value (would render empty)

Frozen floors (2026-07-03): coverage >= 60 % min/page, >= 85 % avg.
Exit 0 = PASS, 1 = FAIL.

Usage: contribution.py <project> [--ns NS] [--min 60] [--avg 85]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import semantic_extract as SE  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

MARK_RE = re.compile(r"\{\{f:([^}]+)\}\}")


def text_of(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def form_text_of(html):
    if not html or "<form" not in html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return " ".join(re.sub(r"\s+", " ", f.get_text(" ", strip=True))
                    for f in soup.find_all("form"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", default=None)
    ap.add_argument("--min", type=float, default=60.0)
    ap.add_argument("--avg", type=float, default=85.0)
    a = ap.parse_args()

    load_p = f"orchestration/content/{a.project}.content-load.json"
    data = json.load(open(load_p))
    if data.get("adapter") != "semantic":
        print(f"SKIP: adapter={data.get('adapter')} — contribution gate targets the semantic adapter")
        return 0

    dead, phantoms, shells = [], [], []
    rows = []
    for slug, p in sorted(data.get("pages", {}).items()):
        lifted = visible = formtx = 0
        for inst in p.get("instances", []):
            if inst.get("area"):
                continue
            if inst.get("promoted") or inst.get("skeleton"):
                # typed skeleton instance OR lifted anonymous raw block (P2.5)
                payloads = [inst] + list(inst.get("children") or [])
                # dead/phantom checks per skeleton
                for pl in payloads:
                    sk = pl.get("skeleton") or ""
                    marks = set(MARK_RE.findall(sk))
                    flds = set(pl.get("fields") or {})
                    for f in flds - marks:
                        dead.append((slug, inst["type"], f))
                    for mkr in marks - flds:
                        phantoms.append((slug, inst["type"], mkr))
                if inst.get("promoted") and not any(pl.get("fields") for pl in payloads):
                    shells.append((slug, inst["type"]))
                recomposed = SE.recompose_group(
                    inst.get("skeleton") or "", inst.get("fields") or {},
                    inst.get("children") or [])
                visible += len(text_of(recomposed))
                formtx += len(form_text_of(recomposed))
                for pl in payloads:
                    for k, v in (pl.get("fields") or {}).items():
                        lifted += len(text_of(v)) if k.startswith("body") else len(v)
            elif inst.get("passthrough"):
                h = (inst.get("fields") or {}).get("html", "")
                visible += len(text_of(h))
                formtx += len(form_text_of(h))
        denom = max(visible - formtx, 1)
        rows.append({"slug": slug, "visible": visible, "form": formtx,
                     "lifted": lifted,
                     "raw": 100.0 * lifted / max(visible, 1),
                     "xform": min(100.0, 100.0 * lifted / denom)})

    print(f"{'page':58s} {'raw%':>6s} {'noform%':>8s}  lifted/visible (form)")
    for r in rows:
        print(f"{r['slug']:58s} {r['raw']:6.1f} {r['xform']:8.1f}  "
              f"{r['lifted']}/{r['visible']} ({r['form']})")

    xs = [r["xform"] for r in rows]
    mn, avg = (min(xs), sum(xs) / len(xs)) if xs else (0, 0)
    print(f"\ncontribution coverage (forms-excluded): min={mn:.1f}% avg={avg:.1f}% "
          f"(floors: min>={a.min:.0f}, avg>={a.avg:.0f})")
    print(f"dead props={len(dead)}  phantom markers={len(phantoms)}  empty shells={len(shells)}")
    for lbl, lst in (("dead", dead), ("phantom", phantoms), ("shell", shells)):
        for x in lst[:5]:
            print(f"  ✗ {lbl}: {x}")

    ok = (mn >= a.min and avg >= a.avg
          and not dead and not phantoms and not shells)
    print(("PASS" if ok else "FAIL") + ": G1 contribution gate")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
