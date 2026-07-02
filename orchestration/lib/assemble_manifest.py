#!/usr/bin/env python3
"""assemble_manifest.py — Deterministic manifest assembler (lever 1 + 2 + 3).

The LLM now outputs ONLY a GROUPING (a partition of the deterministic content
candidate ids) plus a few enum/bool decisions. This script turns that grouping
into the final Jahia component-manifest — computing every NAME deterministically
from the candidate roles, so naming variance across LLM runs is 0 by construction.

Levers:
  1. nodeType / fields / child types are COMPUTED here, never chosen by the LLM.
  2. no-new-types + full-coverage partition gate: any group member that is not a
     known content-candidate id (hallucination) or any uncovered candidate FAILS.
  3. --consensus fuses N grouping files by majority co-membership before assembling.

Cross-cutting components are taken deterministically from the candidate set
(crossCutting[]), never from the LLM.

Usage:
  # single grouping -> manifest (also runs the partition gate)
  python3 assemble_manifest.py <candidates.json> --group <grouping.json> --out <manifest.json>
  # consensus over many groupings -> manifest
  python3 assemble_manifest.py <candidates.json> --consensus <dir/group-*.json ...> --out <manifest.json>
"""
import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations


def camel(role):
    parts = re.split(r"[^a-zA-Z0-9]+", role or "")
    parts = [p for p in parts if p]
    if not parts:
        return "component"
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def title_case(role):
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", role or "") if p]
    return " ".join(p.capitalize() for p in parts) or "Component"


FIELD_MAP = {
    "title:string": {"name": "title", "type": "string", "i18n": True, "mandatory": True},
    "text:string": {"name": "text", "type": "string, richtext", "i18n": True, "mandatory": False},
    "body:richtext": {"name": "body", "type": "string, richtext", "i18n": True, "mandatory": False},
    "image:weakref": {"name": "image", "type": "weakreference, picker[type='image']", "i18n": False, "mandatory": False},
    "images:weakref[]": {"name": "image", "type": "weakreference, picker[type='image']", "i18n": False, "mandatory": False},
    "link:linkType": {"name": "j:linkType", "type": "string, choicelist[linkTypeInitializer]", "i18n": False, "mandatory": False},
    "links:linkType[]": {"name": "j:linkType", "type": "string, choicelist[linkTypeInitializer]", "i18n": False, "mandatory": False},
}


def fields_from_shape(shape):
    out, seen = [], set()
    for tok in shape or []:
        f = FIELD_MAP.get(tok)
        if f and f["name"] not in seen:
            out.append(dict(f))
            seen.add(f["name"])
    return out


def load(p):
    return json.load(open(p))


# ── consensus: majority co-membership -> connected components ──

def consensus_groups(content_ids, grouping_files):
    partitions = []
    for gf in grouping_files:
        g = load(gf)
        idset = []
        for grp in g.get("groups", []):
            members = [m for m in grp.get("members", []) if m in content_ids]
            if members:
                idset.append(set(members))
        partitions.append(idset)

    # count co-membership per pair
    co = Counter()
    present = Counter()
    for part in partitions:
        flat = set().union(*part) if part else set()
        for a, b in combinations(sorted(content_ids), 2):
            if a in flat and b in flat:
                present[(a, b)] += 1
                if any(a in s and b in s for s in part):
                    co[(a, b)] += 1

    # union-find on majority edges
    parent = {i: i for i in content_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    n = len(partitions)
    for (a, b), seen in present.items():
        if seen and co[(a, b)] >= (seen / 2.0) and co[(a, b)] * 2 > seen:
            union(a, b)
    # (strict majority: co > seen/2)

    comps = defaultdict(list)
    for i in content_ids:
        comps[find(i)].append(i)
    groups = [sorted(v) for v in comps.values()]

    # aggregate group-level decisions by majority across runs
    def modal_decisions(members):
        mset = set(members)
        containers = 0
        mainres = 0
        layout_votes = Counter()
        views_votes = Counter()
        total = 0
        for gf in grouping_files:
            g = load(gf)
            for grp in g.get("groups", []):
                gm = set(m for m in grp.get("members", []) if m in content_ids)
                if gm & mset:
                    total += 1
                    if grp.get("kind") == "container":
                        containers += 1
                    if grp.get("needsMainResource"):
                        mainres += 1
                    lp = grp.get("layoutProperty")
                    if isinstance(lp, dict) and lp.get("name"):
                        layout_votes[lp["name"]] += 1
                    for v in grp.get("views", []) or []:
                        if isinstance(v, dict) and v.get("name"):
                            views_votes[v["name"]] += 1
        return {
            "container": total and containers * 2 > total,
            "mainResource": total and mainres * 2 > total,
            "layoutName": layout_votes.most_common(1)[0][0] if layout_votes else None,
            "views": [v for v, _ in views_votes.most_common()] or ["default"],
        }

    return groups, modal_decisions


def single_groups(content_ids, grouping_file):
    g = load(grouping_file)
    groups, raw = [], []
    for grp in g.get("groups", []):
        members = [m for m in grp.get("members", []) if m in content_ids]
        if not members:
            continue
        groups.append(sorted(members))
        lp = grp.get("layoutProperty")
        raw.append((set(members), {
            "container": grp.get("kind") == "container",
            "mainResource": bool(grp.get("needsMainResource")),
            "layoutName": lp.get("name") if isinstance(lp, dict) else None,
            "layoutOptions": lp.get("options") if isinstance(lp, dict) else None,
            "views": [v.get("name") for v in (grp.get("views") or []) if isinstance(v, dict)] or ["default"],
        }))

    def decide(members):
        # find the original group with the largest overlap (robust to sanitizer splits)
        ms = set(members)
        best, bestn = {}, 0
        for orig, dec in raw:
            n = len(ms & orig)
            if n > bestn:
                bestn, best = n, dec
        return best

    return groups, decide, g.get("templates", [])


def _role_tokens(role):
    return set(t for t in re.split(r"[^a-zA-Z0-9]+", (role or "").lower()) if len(t) > 2)


def _compatible(a, b):
    """Two candidate members belong in the same Jahia type only if their editable
    shapes are compatible — kills LLM grab-bags that merge incompatible shapes."""
    sa, sb = set(a["dataShape"]), set(b["dataShape"])
    ca, cb = set(a.get("childShape") or []), set(b.get("childShape") or [])
    role_overlap = bool(_role_tokens(a["role"]) & _role_tokens(b["role"]))

    if not sa and not sb:
        # both empty own-shape: identity is the child items or role kinship
        return bool(ca and cb and (ca & cb)) or role_overlap
    if bool(sa) != bool(sb):
        # one empty own-shape, one not: only same-family (shared role token) merges
        return role_overlap
    # both non-empty own-shape: compatible if one subsumes the other or they overlap
    return sa <= sb or sb <= sa or bool(sa & sb)


def sanitize_groups(groups, by_id):
    """Split any LLM group whose members are not pairwise shape-compatible into
    its compatibility clusters (union-find). Deterministic anti-grab-bag guard."""
    out = []
    for members in groups:
        recs = [by_id[m] for m in members if m in by_id]
        if len(recs) <= 1:
            out.append(members)
            continue
        parent = {m: m for m in members if m in by_id}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        ids = [m for m in members if m in by_id]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if _compatible(by_id[ids[i]], by_id[ids[j]]):
                    parent[find(ids[i])] = find(ids[j])
        clusters = defaultdict(list)
        for m in ids:
            clusters[find(m)].append(m)
        for cl in clusters.values():
            out.append(sorted(cl))
    return out


def isolate_main_resources(groups, candidates):
    """Deterministic lever: a detected mainResource entity role becomes its OWN
    type, even if the LLM (or the shape sanitizer) merged it into another group.
    A detail page renders its entity node, so the entity must not be diluted into
    a grab-bag (e.g. 'article' merged with image-containers on a shared hero img)."""
    entity_roles = {dt["entityRole"] for dt in candidates.get("detailTemplates", []) or []}
    if not entity_roles:
        return groups
    role_by_id = {c["candidateId"]: c["role"] for c in candidates["components"]}
    entity_ids = {cid for cid, role in role_by_id.items() if role in entity_roles}
    out = []
    for g in groups:
        ents = [m for m in g if m in entity_ids]
        rest = [m for m in g if m not in entity_ids]
        if ents and (rest or len(ents) > 1):
            out.extend([e] for e in ents)     # each entity → its own singleton type
            if rest:
                out.append(rest)
        else:
            out.append(g)
    return out


def assemble(candidates, groups, decide, templates, ns="ns"):
    by_id = {c["candidateId"]: c for c in candidates["components"]}
    groups = sanitize_groups(groups, by_id)   # deterministic anti-grab-bag split
    groups = isolate_main_resources(groups, candidates)  # entity gets its own type

    # Agnostic (no site-specific role names): a member is a poor NAME source if it
    # is a synthesized structural placeholder OR carries no editable data of its own.
    SYNTH = {"generic-container", "div"}

    def generic(c):
        return c["role"] in SYNTH or not c.get("dataShape")

    def lead(members):
        ms = [by_id[m] for m in members if m in by_id]
        # prefer a member with real data + meaningful role; then frequency, coverage
        return max(ms, key=lambda c: (0 if generic(c) else 1,
                                      c["frequency"], c["pageCount"], c["role"]))

    components = []
    for members in sorted(groups, key=lambda g: -sum(by_id[m]["frequency"] for m in g if m in by_id)):
        ms = [by_id[m] for m in members if m in by_id]
        if not ms:
            continue
        ld = lead(members)
        node = f"{ns}:{camel(ld['role'])}"
        # union of dominant shapes
        shape = sorted(set().union(*[set(c["dataShape"]) for c in ms]))
        fields = fields_from_shape(shape)
        is_container = any(c["isContainer"] for c in ms)
        # layout property from variant tokens or LLM decision
        variants = sorted(set().union(*[set(c.get("variantTokens", [])) for c in ms]))
        d = decide(members) if callable(decide) else decide.get(tuple(sorted(members)), {})
        layout = None
        if d.get("layoutName") and (len(variants) >= 2 or d.get("layoutOptions")):
            layout = {"name": camel(d["layoutName"]),
                      "options": d.get("layoutOptions") or variants}
        elif len(variants) >= 2:
            layout = {"name": "layout", "options": variants}
        child = None
        if is_container:
            cs = next((c["childShape"] for c in ms if c.get("childShape")), None)
            child_fields = fields_from_shape(cs) if cs else []
            child = {
                "name": title_case(ld["role"]) + " Item",
                "nodeType": f"{ns}:{camel(ld['role'])}Item",
                "fields": child_fields or [{"name": "title", "type": "string", "i18n": True, "mandatory": False}],
            }
        components.append({
            "name": title_case(ld["role"]),
            "nodeType": node,
            "coversRoles": [c["role"] for c in ms],
            "isContainer": is_container,
            "childType": child,
            "needsMainResource": bool(d.get("mainResource")),
            "layoutProperty": layout,
            "views": [{"name": v} for v in (d.get("views") or ["default"])],
            "fields": fields,
            "frequency": sum(c["frequency"] for c in ms),
        })

    # ── detail-page (mainResource) flagging — deterministic, from semantic_extract ──
    # A detected detail cluster names an entity role; the component that covers it
    # (or, failing that, the most of its facet roles) is a mainResource type and
    # gets a fullPage template. This is what unblocks pixel-perfect detail pages.
    detail_tpls = candidates.get("detailTemplates", []) or []
    entity_map = {dt["entityRole"]: dt for dt in detail_tpls}
    extra_templates = []
    for dt in detail_tpls:
        facets = set(dt.get("facetRoles", []))
        target, best = None, 0
        for comp in components:
            covers = set(comp["coversRoles"])
            if dt["entityRole"] in covers:            # direct hit on the entity role
                target, best = comp, 10_000
                break
            overlap = len(covers & facets)            # fallback: covers most facets
            if overlap > best:
                target, best = comp, overlap
        if not target or best < 1:
            continue
        target["needsMainResource"] = True
        target["detailOf"] = dt["detailOf"]
        extra_templates.append({
            "name": camel(dt["detailOf"]) + "Detail",
            "kind": "detail",
            "pages": dt["pages"],
            "mainResourceType": target["nodeType"],
            "listingOf": dt["detailOf"],
            "listingPageExists": dt.get("listingPageExists", False),
            "confidence": dt.get("confidence"),
        })

    seen_names = {t.get("name") for t in templates if isinstance(t, dict)}
    templates = list(templates) + [t for t in extra_templates if t["name"] not in seen_names]

    # cross-cutting: deterministic from candidate set
    xcut = []
    for c in candidates.get("crossCutting", []):
        xcut.append({
            "name": title_case(c["role"]),
            "nodeType": f"{ns}:{camel(c['role'])}",
            "area": "nav" if "nav" in c["role"] else c["position"],
            "fields": fields_from_shape(c["dataShape"]),
            "coversRole": c["role"],
        })

    return {"crossCutting": xcut, "components": components, "templates": templates,
            "typeCount": len(components)}


def partition_gate(candidates, groups):
    content_ids = set(c["candidateId"] for c in candidates["components"])
    used = [m for g in groups for m in g]
    used_set = set(used)
    unknown = [m for m in used if m not in content_ids]
    missing = sorted(content_ids - used_set)
    dupes = [m for m, k in Counter(used).items() if k > 1]
    return unknown, missing, dupes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--group")
    ap.add_argument("--consensus", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ns", default="ns", help="module namespace prefix (agnostic; e.g. usg)")
    args = ap.parse_args()

    cand = load(args.candidates)
    content_ids = set(c["candidateId"] for c in cand["components"])

    if args.consensus:
        files = []
        for pat in args.consensus:
            files += sorted(glob.glob(pat)) if any(ch in pat for ch in "*?[") else [pat]
        groups, decide = consensus_groups(content_ids, files)
        templates = []  # templates handled separately at consensus (kept from modal below)
        # pick templates from the run with the median template count
        tcs = []
        for gf in files:
            g = load(gf)
            tcs.append((len(g.get("templates", []) or []), g.get("templates", [])))
        tcs.sort(key=lambda x: x[0])
        templates = tcs[len(tcs) // 2][1] if tcs else []
    else:
        groups, decide, templates = single_groups(content_ids, args.group)

    unknown, missing, dupes = partition_gate(cand, groups)
    manifest = assemble(cand, groups, decide, templates, ns=args.ns)

    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[assemble] {args.out}: {len(manifest['components'])} components, "
          f"{len(manifest['crossCutting'])} cross-cutting, {len(templates)} templates")
    gate_ok = True
    if unknown:
        print(f"  [no-new-types] FAIL — hallucinated/unknown ids: {unknown}")
        gate_ok = False
    if missing:
        print(f"  [coverage] FAIL — candidates not assigned to any group: {missing}")
        gate_ok = False
    if dupes:
        print(f"  [partition] FAIL — ids in >1 group: {dupes}")
        gate_ok = False
    if gate_ok:
        print("  [partition gate] PASS — exact partition of content candidates")
    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
