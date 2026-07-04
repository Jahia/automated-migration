#!/usr/bin/env python3
"""composability.py — the COMPOSABILITY-DEBT instrument (MODULARITY-PLAN P6, Pillar 4).

The blind spot this measures: G1 scores editable TEXT, G6 scores whether the
wired fields are reachable — but neither scores editable STRUCTURE. A migration
can be pixel-perfect and text-editable yet still ship "one big component for the
whole page with as many properties as needed" (Julian, 2026-07-04). That model
is NOT composable: the contributor edits text inside frozen sections but cannot
add / reorder / remove blocks. This probe quantifies exactly that debt so P6.2
decomposition can be measured against a baseline.

READ-ONLY. No Jahia, no mutation, no network. It reads three on-disk artifacts:

  projects/<p>/settings/definitions.cnd                     -> the type model
  projects/<p>/workflow-output/component-manifest.json      -> vision naming
  orchestration/content/<p>.content-load.json               -> the instance tree
    (falls back to projects/<p>/workflow-output/definitions.cnd for the CND)

Metrics printed, per project:

  TYPES        total concrete CND types; composable containers (a type whose
               CND body declares `+ * (...)` or `+ named (...)`) vs leaf types;
               "frozen" types (a type declaring a `skeleton` / `html` / `body*`
               property — structure baked into markup, not children).

  STRUCTURE    composable ratio = share of *instance nodes* that are typed atoms
               (a typed semantic node carrying no page-sized skeleton) vs frozen
               blobs (rawHtml passthrough OR any node carrying a `skeleton`).
               This is the headline "typed-composable vs skeleton" number.

  K (lift)     max lifted editor fields on any single instance of a type
               = |fields minus {html,skeleton}| + |media| + (1 if link). Types
               over the K threshold are the "page-in-one-component" anti-pattern:
               beyond K a type must decompose into child nodes. Default K=8.

  MONOLITHS    typed/promoted nodes whose skeleton is page-sized (>= MONO bytes,
               default 8000) — one node standing in for a whole page/section.

A global DEBT NOTE + a per-type table are printed.

─────────────────────────────────────────────────────────────────────────────
THE GATE CONTRACT (calibrated P6.1, K=8 locked by Julian 2026-07-04)
─────────────────────────────────────────────────────────────────────────────
Default (--report): REPORTS all metrics and ALWAYS exits 0.

--gate: exit NON-ZERO (fail) iff EITHER
  (a) any content type has an instance carrying > K lifted editor fields
      (K=8; "one big component for the whole page with as many props as needed"
      — beyond K a type MUST decompose into child nodes), OR
  (b) any full-page MONOLITH exists (a node whose frozen skeleton is >= --mono-bytes,
      i.e. one node standing in for a whole page/section).

  The COMPOSABLE RATIO is REPORTED but is NOT part of the hard fail (it only
  becomes blocking once P6.2 decomposition has run and we set a floor — the plan's
  Pillar 4 posture). So the gate today enforces "no page-in-one-component and no
  full-page monolith" without yet demanding a composability minimum.

K CALIBRATION (why K=8 is safe — verified on acquia + supercar, P6.1):
  Every type that exceeds K=8 in the 4 baselines is the DEBT the gate targets: a
  skeleton/body-run aggregate (e.g. acquia content-listing K=27 with 18 body*,
  supercar content K=34 with 18 body*). NO legitimate library-shaped component
  exceeds 8: the richest base-library atom, $NS:card = title+body+image+alt+theme
  +cornerCut = 6 node-level fields (tag/button are CHILD nodes, not lifted fields).
  Even the borderline acquia card types (ct-article--card-wrapper K=9) exceed K
  ONLY because they carry body+body2+body3+body4 (the un-decomposed numbered-run
  anti-pattern) — decomposed to heading+richText+images they fall well under 8.
  So K=8 fails the debt and passes every legitimate rich card. (Any future legit
  case that trips K must be escalated to Julian, not silently raised — §5b.)

Usage:  composability.py <project> [--k 8] [--mono-bytes 8000] [--gate] [--json]
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# ── CND parsing (deliberately minimal: we only need type headers, property
#    names, and child-node declarations — not a full JCR-CND grammar) ──
TYPE_RE = re.compile(r"^\s*\[([\w]+:[\w]+)\]")      # [ns:name] ...
MIXIN_RE = re.compile(r"^\s*\[([\w]+:[\w]+)\].*\bmixin\b")
PROP_RE = re.compile(r"^\s*-\s*([\w:]+)\s*\(")       # - name (type ...)
CHILD_RE = re.compile(r"^\s*\+\s*(\*|[\w:]+)\s*\(([\w:]+)\)")  # + */name (childType)

# properties that FREEZE structure into markup instead of exposing children
FROZEN_PROPS = ("skeleton", "html")
# `body`/`body1` alone is a LEGIT single richtext field (an atom's body — see the
# base library's $NS:richText / $NS:card). The God-object anti-pattern is a NUMBERED
# RUN of body fields (body2, body3, ...): that means N text runs were aggregated onto
# one type instead of decomposed into children (MODULARITY-PLAN §1, migration.md r24).
# BODYN_RE  → any body* field (counted toward K, the lift metric).
# BODYRUN_RE→ body2+ only (the frozen-type / decompose-me marker).
BODYN_RE = re.compile(r"^body\d*$")
BODYRUN_RE = re.compile(r"^body([2-9]|\d{2,})$")


def parse_cnd(path):
    """Return {typeName: {"is_mixin", "supertypes", "props":[...],
    "children":[(childName, childType)], "line"}} for concrete + mixin types."""
    types = {}
    cur = None
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            m = TYPE_RE.match(ln)
            if m:
                name = m.group(1)
                sup = ""
                if ">" in ln:
                    sup = ln.split(">", 1)[1].split("mixin")[0]
                cur = {
                    "name": name,
                    "is_mixin": bool(MIXIN_RE.match(ln)),
                    "supertypes": [s.strip() for s in sup.split(",") if s.strip()],
                    "props": [],
                    "children": [],
                }
                types[name] = cur
                continue
            if cur is None:
                continue
            pm = PROP_RE.match(ln)
            if pm:
                cur["props"].append(pm.group(1))
                continue
            cm = CHILD_RE.match(ln)
            if cm:
                cur["children"].append((cm.group(1), cm.group(2)))
    return types


def cnd_path(project):
    a = os.path.join(ROOT, "projects", project, "settings", "definitions.cnd")
    b = os.path.join(ROOT, "projects", project, "workflow-output", "definitions.cnd")
    if os.path.isfile(a):
        return a
    if os.path.isfile(b):
        return b
    return None


def short(t):
    """Strip the namespace prefix: asr:heroBanner -> heroBanner."""
    return t.split(":", 1)[1] if ":" in t else t


# ── instance-tree analysis (the content-load plan is the runtime truth) ──
def lifted_fields(inst):
    """Editor-facing lifted slots on one instance node.
    Excludes html (passthrough verbatim) and skeleton (hidden frozen markup)."""
    f = inst.get("fields") or {}
    n = sum(1 for k in f if k not in ("html", "skeleton"))
    n += len(inst.get("media") or [])
    n += 1 if inst.get("link") else 0
    return n


def classify(inst):
    """Three legible tiers for the structure ratio:
      'atom'        typed semantic node, no page-sized skeleton -> composable.
                    (As P6.2/P6.3 lifts small typed atoms out of skeletons, this
                    rises.) Includes P6.3 LIBRARY nodes: a libraryAtom (a real
                    typed child, e.g. asr:logo) and a libraryPlan CONTAINER (e.g.
                    asr:logoWall with typed atom children) — the container carries
                    a verbatim `skeleton` ONLY for the byte-exact {{child:N}} LIVE
                    splice (rule 26 fidelity default), NOT the God-object pattern,
                    so it counts as composable structure, not frozen.
      'frozen'      any OTHER node carrying a skeleton (structure baked into
                    markup), including page-sized monoliths.
      'passthrough' rawHtml verbatim blob with no skeleton.
    """
    if inst.get("libraryAtom") or inst.get("libraryPlan"):
        return "atom"
    sk = inst.get("skeleton") or ""
    if sk:
        return "frozen"
    if inst.get("type") == "rawHtml":
        return "passthrough"
    return "atom"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--k", type=int, default=8,
                    help="max lifted fields per type before it must decompose (default 8)")
    ap.add_argument("--mono-bytes", type=int, default=8000,
                    help="skeleton byte size at/above which a node is a full-page monolith")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero on K-exceeded or monolith (default: report-only, exit 0)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON summary")
    a = ap.parse_args()

    cp = cnd_path(a.project)
    if not cp:
        print(f"SKIP: no definitions.cnd for project '{a.project}'")
        return 0
    cnd = parse_cnd(cp)

    load_p = os.path.join(ROOT, "orchestration", "content", f"{a.project}.content-load.json")
    if not os.path.isfile(load_p):
        print(f"SKIP: no content-load plan at {load_p}")
        return 0
    data = json.load(open(load_p))

    # ── CND-level type accounting ──
    concrete = {n: d for n, d in cnd.items() if not d["is_mixin"]}
    containers, leaves, frozen_types = [], [], []
    for n, d in concrete.items():
        composable = bool(d["children"])          # declares + */named child nodes
        # frozen type = structure baked into markup: a skeleton/html blob OR a
        # NUMBERED body run (body2+). A lone `body` is a legit atom richtext field.
        has_frozen = any(p in FROZEN_PROPS or BODYRUN_RE.match(p) for p in d["props"])
        if composable:
            containers.append(n)
        else:
            leaves.append(n)
        if has_frozen:
            frozen_types.append(n)
    # a container is "open" if any child is the wildcard `+ *`
    open_containers = [n for n in containers
                       if any(cn == "*" for cn, _ in concrete[n]["children"])]

    # ── instance-level accounting (drives structure ratio, K, monoliths) ──
    per_type_maxk = {}      # short type -> (max lifted, fieldkeys, imgs, links)
    per_type_count = {}     # short type -> instance count
    per_type_frozen = {}    # short type -> #instances carrying a skeleton
    typed_atoms = 0
    frozen_sections = 0
    passthrough_pure = 0
    monoliths = []          # (page, type, skeleton_bytes, lifted)
    total_inst = 0

    for slug, pv in data.get("pages", {}).items():
        for inst in pv.get("instances", []):
            total_inst += 1
            t = short(inst.get("type") or "?")
            per_type_count[t] = per_type_count.get(t, 0) + 1
            lf = lifted_fields(inst)
            imgs = len(inst.get("media") or [])
            nlnk = 1 if inst.get("link") else 0
            if t not in per_type_maxk or lf > per_type_maxk[t][0]:
                per_type_maxk[t] = (lf, sorted((inst.get("fields") or {}).keys()), imgs, nlnk)
            sk = inst.get("skeleton") or ""
            # a library node's verbatim skeleton is the fidelity default, not a
            # frozen God-object — do not count it toward the frozen/monolith debt.
            is_lib = bool(inst.get("libraryAtom") or inst.get("libraryPlan"))
            if sk and not is_lib:
                per_type_frozen[t] = per_type_frozen.get(t, 0) + 1

            tier = classify(inst)
            if tier == "atom":
                typed_atoms += 1
            elif tier == "frozen":
                frozen_sections += 1
            else:
                passthrough_pure += 1

            if sk and not is_lib and len(sk) >= a.mono_bytes:
                monoliths.append((slug, inst.get("type"), len(sk), lf))

    frozen_blobs = frozen_sections + passthrough_pure
    composable_ratio = 100.0 * typed_atoms / max(total_inst, 1)
    over_k = sorted(
        [(t, per_type_maxk[t][0]) for t in per_type_maxk if per_type_maxk[t][0] > a.k],
        key=lambda x: -x[1])

    # ── report ──
    print(f"COMPOSABILITY DEBT — project '{a.project}'")
    print(f"  CND: {os.path.relpath(cp, ROOT)}")
    print(f"  content-load: {os.path.relpath(load_p, ROOT)}\n")

    print("TYPES (from CND)")
    print(f"  concrete types ............. {len(concrete)}")
    print(f"  composable containers ...... {len(containers)}"
          f"  (open '+ *' palette: {len(open_containers)})")
    print(f"  leaf types ................. {len(leaves)}")
    print(f"  frozen types (skeleton/html/body2+) {len(frozen_types)}")
    print()

    print("STRUCTURE (from content-load instance tree)")
    print(f"  total instance nodes ....... {total_inst}")
    print(f"  typed composable atoms ..... {typed_atoms}"
          f"  (semantic node, no frozen skeleton)")
    print(f"  frozen sections (skeleton) . {frozen_sections}")
    print(f"  pure rawHtml passthrough ... {passthrough_pure}")
    print(f"  (frozen blobs total ........ {frozen_blobs})")
    print(f"  COMPOSABLE RATIO ........... {composable_ratio:.1f}%"
          f"  (typed atoms / all nodes; higher = more composable)")
    print()

    print(f"K — MAX LIFTED FIELDS PER TYPE (anti-pattern threshold K={a.k})")
    if over_k:
        print(f"  {len(over_k)} type(s) exceed K (must decompose into children):")
        for t, k in over_k:
            _, fk, ni, nl = per_type_maxk[t]
            bodyn = [x for x in fk if BODYN_RE.match(x)]
            print(f"    {t:34s} K={k:2d}  ({len(bodyn)} body*, {ni} img, {nl} link)")
    else:
        print(f"  none exceed K={a.k}")
    print()

    print(f"FULL-PAGE MONOLITHS (skeleton >= {a.mono_bytes} bytes)")
    if monoliths:
        print(f"  {len(monoliths)} monolith node(s) — one node standing in for a whole page/section:")
        for slug, ty, nb, lf in sorted(monoliths, key=lambda x: -x[2])[:10]:
            print(f"    {slug:32s} {ty:16s} skeleton={nb:>8,d}B  lifted={lf}")
    else:
        print("  none")
    print()

    print(f"{'type':34s} {'#inst':>5s} {'maxK':>4s} {'frozen#':>7s}")
    for t in sorted(per_type_maxk, key=lambda x: (-per_type_maxk[x][0], -per_type_count.get(x, 0))):
        print(f"{t:34s} {per_type_count.get(t,0):5d} {per_type_maxk[t][0]:4d} "
              f"{per_type_frozen.get(t,0):7d}")
    print()

    # ── debt note ──
    note = []
    if composable_ratio < 25:
        note.append(f"CRITICAL: only {composable_ratio:.1f}% of nodes are typed atoms — the "
                    "model is capture-and-freeze, not recognize-and-compose.")
    elif composable_ratio < 60:
        note.append(f"HIGH: {composable_ratio:.1f}% typed atoms — skeleton still dominates.")
    else:
        note.append(f"OK: {composable_ratio:.1f}% typed atoms.")
    if over_k:
        note.append(f"{len(over_k)} type(s) over K={a.k} (page-in-one-component). "
                    f"worst: {over_k[0][0]}={over_k[0][1]}.")
    if monoliths:
        note.append(f"{len(monoliths)} full-page monolith(s) present.")
    if not open_containers:
        note.append("no open '+ *' container palette — editor cannot freely add blocks.")
    print("DEBT NOTE: " + " ".join(note))

    # HARD GATE (calibrated P6.1): fail on any K>threshold instance OR any full-page
    # monolith. The composable RATIO is reported above but NOT part of the fail
    # (it becomes a floor only after P6.2 decomposition runs — see the gate contract
    # in this file's header). exit 0/1 accordingly under --gate.
    fail = bool(over_k) or bool(monoliths)
    if a.gate:
        reasons = []
        if over_k:
            reasons.append(f"{len(over_k)} type(s) over K={a.k} (worst {over_k[0][0]}={over_k[0][1]})")
        if monoliths:
            reasons.append(f"{len(monoliths)} full-page monolith(s)")
        verdict = "FAIL" if fail else "PASS"
        print(f"{verdict}: composability HARD gate (K={a.k}, mono>={a.mono_bytes}B)"
              + (" — " + "; ".join(reasons) if reasons else "")
              + f"  [ratio {composable_ratio:.1f}% reported, not gated]")
    else:
        print("REPORT-ONLY: not gating — exit 0 regardless of debt "
              "(pass --gate to enforce the hard K/monolith gate)")

    if a.json:
        print(json.dumps({
            "project": a.project,
            "types": {"concrete": len(concrete), "containers": len(containers),
                      "openContainers": len(open_containers), "leaves": len(leaves),
                      "frozenTypes": len(frozen_types)},
            "structure": {"totalNodes": total_inst, "typedAtoms": typed_atoms,
                          "frozenSections": frozen_sections,
                          "purePassthrough": passthrough_pure,
                          "frozenBlobs": frozen_blobs,
                          "composableRatio": round(composable_ratio, 1)},
            "k": {"threshold": a.k, "overK": over_k},
            "monoliths": len(monoliths),
        }, indent=2))

    return (1 if (fail and a.gate) else 0)


if __name__ == "__main__":
    sys.exit(main())
