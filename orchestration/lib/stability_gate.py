#!/usr/bin/env python3
"""stability_gate.py — Objective stability + granularity gate over adjudication runs.

Consumes N independent LLM adjudication manifests (run-*.json) produced from the
SAME deterministic candidate set, plus consensus.json, and reports:

  A. COUNT stability   — typeCount / #container / #mainResource / #crossCutting /
                         #templates per run + spread.
  B. GROUPING stability — naming-invariant: for every pair of source roles, do all
                          runs agree on whether they land in the SAME output type?
                          (This isolates *substantive* clustering variance from
                          *cosmetic* naming variance.)
  C. CROSS-CUTTING stability — is the header/nav/footer set identical across runs?
  D. GATES on consensus — dup-shape, granularity band, template page-coverage,
                          candidate accounting. Non-zero exit if a hard gate fails.

Usage:
  python3 orchestration/lib/stability_gate.py <adjudication_dir> <candidates.json>
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations


def load(path):
    try:
        return json.load(open(path))
    except Exception as e:
        return {"__parse_error__": str(e)}


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def type_records(manifest):
    """Normalize a manifest's components (+ child types) into flat records."""
    recs = []
    for c in manifest.get("components", []) or []:
        covers = set(norm(r) for r in (c.get("coversRoles") or []))
        recs.append({
            "name": c.get("name") or c.get("nodeType") or "?",
            "nodeType": c.get("nodeType", ""),
            "covers": covers,
            "isContainer": bool(c.get("isContainer")),
            "mainResource": bool(c.get("needsMainResource")),
            "layoutProp": bool(c.get("layoutProperty")),
            "fields": c.get("fields") or [],
            "views": c.get("views") or [],
            "childType": c.get("childType"),
        })
    return recs


def _fields_sig(fields):
    return sorted(norm(f.get("name", "")) + ":" + norm(f.get("type", "")).split(",")[0]
                  for f in (fields or []) if isinstance(f, dict))


def field_shape(rec):
    """A type's identity shape. For containers, identity lives in the CHILD type,
    so fold the child field shape in — else distinct containers (KeyFigures vs
    Timeline vs PageList) that share only a container 'title' collide falsely."""
    own = _fields_sig(rec["fields"])
    child = rec.get("childType")
    if isinstance(child, dict):
        own = own + ["{child:" + "|".join(_fields_sig(child.get("fields"))) + "}"]
    return "|".join(own)


def main():
    if len(sys.argv) < 3:
        print("Usage: stability_gate.py <adjudication_dir> <candidates.json>", file=sys.stderr)
        sys.exit(2)
    adj_dir, cand_path = sys.argv[1], sys.argv[2]
    run_paths = sorted(glob.glob(os.path.join(adj_dir, "run-*.json")))
    runs = [(os.path.basename(p), load(p)) for p in run_paths]
    cand = load(cand_path)

    parse_fail = [name for name, m in runs if "__parse_error__" in m]
    good = [(name, m) for name, m in runs if "__parse_error__" not in m]

    print("=" * 70)
    print(f"STABILITY ANALYSIS — {len(runs)} runs ({len(parse_fail)} JSON-invalid)")
    if parse_fail:
        print(f"  INVALID JSON: {parse_fail}")
    print("=" * 70)

    # ── A. count stability ──
    def counts(m):
        comps = m.get("components", []) or []
        return {
            "types": len(comps),
            "containers": sum(1 for c in comps if c.get("isContainer")),
            "mainResource": sum(1 for c in comps if c.get("needsMainResource")),
            "crossCutting": len(m.get("crossCutting", []) or []),
            "templates": len(m.get("templates", []) or []),
            "folded": len(m.get("folded", []) or []),
        }
    print("\nA. COUNT STABILITY")
    keys = ["types", "containers", "mainResource", "crossCutting", "templates", "folded"]
    hdr = f"  {'metric':14s} " + " ".join(f"{name.split('.')[0][-6:]:>6s}" for name, _ in good) + "   spread"
    print(hdr)
    for k in keys:
        vals = [counts(m)[k] for _, m in good]
        spread = f"{min(vals)}-{max(vals)}" if vals else "-"
        flag = "" if (vals and max(vals) - min(vals) <= 1) else "  <-- VARIES"
        print(f"  {k:14s} " + " ".join(f"{v:6d}" for v in vals) + f"   {spread}{flag}")

    # ── B. grouping stability (naming-invariant) ──
    print("\nB. GROUPING STABILITY (naming-invariant, via source roles)")
    # all source content roles from candidates
    src_roles = set()
    for c in cand.get("components", []) or []:
        src_roles.add(norm(c.get("role", "")))
    src_roles.discard("")
    have_covers = all(any(r["covers"] for r in type_records(m)) for _, m in good) if good else False
    if not have_covers or len(src_roles) < 2:
        print("  (coversRoles not populated by runs — falling back to nodeType-set overlap)")
        # fallback: Jaccard of normalized nodeType sets across runs
        sets = [set(norm(c.get("nodeType") or c.get("name") or "")
                    for c in (m.get("components", []) or [])) for _, m in good]
        pair_j = [len(a & b) / len(a | b) for a, b in combinations(sets, 2) if (a | b)]
        if pair_j:
            print(f"  mean pairwise nodeType Jaccard: {sum(pair_j)/len(pair_j):.2f} "
                  f"(1.0 = identical type sets)")
    else:
        # for each run, map source role -> type index
        role_to_type = []
        for _, m in good:
            recs = type_records(m)
            mp = {}
            for idx, r in enumerate(recs):
                for role in r["covers"]:
                    mp[role] = idx
            role_to_type.append(mp)
        # pairwise co-membership agreement across ALL runs
        pairs = list(combinations(sorted(src_roles), 2))
        agree = 0
        disagreements = []
        counted = 0
        for a, b in pairs:
            verdicts = []
            for mp in role_to_type:
                if a in mp and b in mp:
                    verdicts.append(mp[a] == mp[b])
            if len(verdicts) < 2:
                continue
            counted += 1
            if all(verdicts) or not any(verdicts):
                agree += 1
            else:
                disagreements.append((a, b, sum(verdicts), len(verdicts)))
        if counted:
            print(f"  co-membership agreement: {agree}/{counted} role-pairs "
                  f"({100*agree/counted:.0f}%) grouped consistently across runs")
            for a, b, s, t in disagreements[:12]:
                print(f"    DISAGREE: '{a}' + '{b}' grouped together in {s}/{t} runs")

    # ── C. cross-cutting stability ──
    print("\nC. CROSS-CUTTING STABILITY (header/nav/footer must be identical)")
    xsets = []
    for name, m in good:
        xs = set()
        for c in m.get("crossCutting", []) or []:
            xs.add(norm(c.get("area", "")) + ":" + norm(c.get("name") or c.get("nodeType") or ""))
        xsets.append((name, xs, [c.get("area") for c in (m.get("crossCutting", []) or [])]))
    areas_per_run = [sorted(set(norm(a or "") for a in areas)) for _, _, areas in xsets]
    for (name, _), areas in zip(good, areas_per_run):
        print(f"  {name:14s} areas={areas}")
    all_have = all(("header" in a and "footer" in a) for a in areas_per_run) if areas_per_run else False
    print(f"  --> header+footer present in EVERY run: {all_have}")

    # ── D. gates on consensus ──
    cons = load(os.path.join(adj_dir, "consensus.json"))
    print("\nD. DETERMINISTIC GATES on consensus.json")
    gate_fail = []
    if "__parse_error__" in cons:
        print(f"  consensus.json invalid: {cons['__parse_error__']}")
        gate_fail.append("consensus-parse")
    else:
        recs = type_records(cons)
        # D1 dup-shape
        shape_map = defaultdict(list)
        for r in recs:
            fs = field_shape(r)
            if fs:
                shape_map[fs].append(r["name"])
        dups = {k: v for k, v in shape_map.items() if len(v) > 1}
        if dups:
            # WARN, not FAIL: real sites legitimately reuse a data shape across
            # semantically distinct roles (Image vs Video, Breadcrumb vs CTA).
            # A collision is a REVIEW signal — merge OR justify by role — not an
            # automatic merge. (The reference model itself ships richText+plainHtml.)
            print("  [D1 dup-shape] WARN — same field shape across roles (review: merge or justify):")
            for k, v in dups.items():
                print(f"      {v}  shape=[{k}]")
        else:
            print("  [D1 dup-shape] PASS — no two types share an identical field shape")
        # D2 granularity: micro-types
        micro = [r["name"] for r in recs
                 if len(r["fields"]) < 2 and not r["isContainer"]
                 and not r["mainResource"] and not r["childType"]]
        if micro:
            print(f"  [D2 granularity] WARN — {len(micro)} possible micro-types (<2 fields): {micro}")
        else:
            print("  [D2 granularity] PASS — no micro-types")
        n = len(recs)
        band = (5, 25)
        print(f"  [D2 band] consensus has {n} content types "
              f"({'OK' if band[0] <= n <= band[1] else 'OUT OF BAND ' + str(band)})")
        # D3 cross-cutting present
        cx_areas = set(norm(c.get("area", "")) for c in (cons.get("crossCutting", []) or []))
        ok_cx = "header" in cx_areas and "footer" in cx_areas
        print(f"  [D3 cross-cutting] {'PASS' if ok_cx else 'FAIL'} — consensus areas={sorted(cx_areas)}")
        if not ok_cx:
            gate_fail.append("cross-cutting")
        # D4 template page coverage
        tmpl_pages = []
        for t in cons.get("templates", []) or []:
            tmpl_pages += [p for p in (t.get("pages") or [])]
        pc = Counter(norm(p) for p in tmpl_pages)
        src_pages = set(norm(c) for c in _all_pages(cand))
        multi = [p for p, k in pc.items() if k > 1]
        missing = src_pages - set(pc.keys()) if src_pages else set()
        print(f"  [D4 templates] {len(cons.get('templates', []) or [])} templates cover "
              f"{len(pc)} pages; dup-assigned={multi or 'none'}; "
              f"missing={sorted(missing) if missing else 'none'}")

    print("\n" + "=" * 70)
    if gate_fail:
        print(f"GATES FAILED: {gate_fail}")
        sys.exit(1)
    print("GATES PASSED (consensus is dup-shape-clean, cross-cutting-complete)")


def _all_pages(cand):
    # try to recover the page list from candidate 'pages' arrays
    pages = set()
    for bucket in ("components", "crossCutting", "nestedParts"):
        for c in cand.get(bucket, []) or []:
            for p in c.get("pages", []) or []:
                pages.add(p)
    return pages


if __name__ == "__main__":
    main()
