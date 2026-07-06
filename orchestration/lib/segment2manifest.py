#!/usr/bin/env python3
"""segment2manifest.py — vision segmentation -> component manifest (QUALITY-PLAN P2.2).

Naming authority = the vision model's editorial names (pre-registered); everything
else is DETERMINISTIC re-derivation from the data-seg-annotated DOM the probe
dumped (`segment/<slug>.dom.html`):

  - cross-page aggregation by normalized component name (stable ids)
  - per-segment FIELD re-extraction (semantic_extract.extract_fields on the
    [data-seg] subtree, children as boundaries) — the vision output has no
    dataShape by design
  - heuristic role of each segment root (role_and_variants) — bridges the two
    vocabularies: extract_content emits heuristic-role instances, and the
    manifest's instanceTypeMap maps them onto the vision-named nodeTypes
  - chrome kind -> crossCutting (absolute areas); detail templates reused from
    semantic-templates.json (vocabulary-independent)
  - representative markup -> workflow-output/html-fragments/<vision-role>.html

The heuristics thus become the PRIOR/FALLBACK (positions, shapes, detail
detection) while the vision decides the segmentation + names (P2.2 contract).

Writes: workflow-output/component-manifest.json (--out to override)
        workflow-output/promote-roles.json (heuristic roles the vision covers —
        feeds passthrough-overrides.json promoteRoles for the semantic load)

Usage: segment2manifest.py <project> --ns NS [--out PATH]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup  # noqa: E402
import semantic_extract as SE  # noqa: E402
from assemble_manifest import camel, title_case, fields_from_shape, naming_violations  # noqa: E402


def norm_name(name):
    """'Article Card' -> 'article-card' (the cross-page stable id)."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "component"


# ── type consolidation (component-model doctrine, 2026-07-06) ────────────────
# Per-page segmentation of every inventory page makes the vision name the same
# component drift across pages ("Brands Logo" / "Brand Logos" / "Brand Logo
# Grid"). Near-duplicate aggregates MERGE deterministically before type
# emission; every absorbed key stays as an instanceTypeMap ALIAS so per-page
# extraction still resolves the original vision names.

_GENERIC_TOKENS = {"section", "component", "block", "content", "area",
                   "the", "a", "an", "of", "and", "with"}


def _tokens(key):
    """Singularized, generic-word-free token set of a norm-name key."""
    toks = set()
    for t in (key or "").split("-"):
        t = t.lower()
        if t.endswith("s") and len(t) > 3:
            t = t[:-1]
        if t and t not in _GENERIC_TOKENS:
            toks.add(t)
    return toks


def _tok_jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dominant_shape(e):
    from collections import Counter
    return set(Counter(e["shapes"]).most_common(1)[0][0]) if e["shapes"] else set()


def _shape_compat(e1, e2):
    """Dominant-shape field overlap; sparse shapes (<=1 field) never veto."""
    s1, s2 = _dominant_shape(e1), _dominant_shape(e2)
    if len(s1) <= 1 or len(s2) <= 1:
        return True
    return len(s1 & s2) / len(s1 | s2) >= 0.5


def _merge_into(agg, winner, loser):
    w, l = agg[winner], agg[loser]
    w["shapes"] += l["shapes"]
    w["childShapes"] += l["childShapes"]
    w["heurRoles"] |= l["heurRoles"]
    w["pages"] |= l["pages"]
    w["frequency"] += l["frequency"]
    w["interactive"] = w["interactive"] or l["interactive"]
    w["boxes"] += l["boxes"]
    if l["fragment"] and (w["fragment"] is None
                          or len(l["fragment"][1]) > len(w["fragment"][1])):
        w["fragment"] = l["fragment"]
    if l["kind"] == "container":     # any container variant means child items exist
        w["kind"] = "container"
    w.setdefault("aliases", set()).add(loser)
    w["aliases"] |= l.get("aliases", set())
    del agg[loser]


def consolidate_types(agg):
    """Merge near-duplicate aggregates in place. Two aggregates merge when they
    are both chrome or both non-chrome, their dominant shapes are compatible,
    and EITHER their token-set Jaccard >= 0.6 (brand-logos ~ brand-logo-grid)
    OR they share a >= 2-token name prefix family (section-heading-inspiration
    ~ section-heading-follow-us -> merged under 'section-heading').
    Deterministic: keys processed by (-frequency, len, alpha); winner is the
    higher-frequency (then shorter, then alphabetical) key.
    Returns the merge log [{into, merged, rule}]."""
    log = []

    # pass 1: prefix families — >= 2 keys sharing their first 2 tokens merge
    # under the bare prefix key (created if absent).
    from collections import defaultdict
    fams = defaultdict(list)
    for k in list(agg):
        parts = k.split("-")
        if len(parts) >= 2:
            fams["-".join(parts[:2])].append(k)
    for prefix, keys in sorted(fams.items()):
        members = [k for k in keys if k in agg]
        if len(members) < 2:
            continue
        kinds = {"chrome" if agg[k]["kind"] == "chrome" else "content" for k in members}
        if len(kinds) > 1:
            continue
        base = [k for k in members if _shape_compat(agg[members[0]], agg[k])]
        if len(base) < 2:
            continue
        if prefix in agg:
            winner = prefix
        else:
            # rename the strongest member to the bare prefix — the family's
            # clean editorial name ('Section Heading', not '... Inspiration');
            # the original key survives as an instanceTypeMap alias.
            best = min(base, key=lambda k: (-agg[k]["frequency"], len(k), k))
            agg[prefix] = agg.pop(best)
            agg[prefix]["name"] = title_case(prefix)
            agg[prefix].setdefault("aliases", set()).add(best)
            log.append({"into": prefix, "merged": best, "rule": f"prefix-rename:{prefix}"})
            winner = prefix
        for k in sorted(base):
            if k == winner or k not in agg:
                continue
            _merge_into(agg, winner, k)
            log.append({"into": winner, "merged": k, "rule": f"prefix-family:{prefix}"})

    # pass 2: pairwise token-set Jaccard >= 0.6 (winner-absorbs, re-scanned
    # until stable so chains like a~b~c collapse fully).
    changed = True
    while changed:
        changed = False
        keys = sorted(agg, key=lambda k: (-agg[k]["frequency"], len(k), k))
        for i, w in enumerate(keys):
            if w not in agg:
                continue
            for l in keys[i + 1:]:
                if l not in agg or w not in agg:
                    continue
                same_class = (agg[w]["kind"] == "chrome") == (agg[l]["kind"] == "chrome")
                if not same_class:
                    continue
                tw, tl = _tokens(w), _tokens(l)
                small, big = (tw, tl) if len(tw) <= len(tl) else (tl, tw)
                # near-identical token sets, or one name a strict refinement of
                # the other by a single token ('footer' ~ 'site-footer').
                near = _tok_jaccard(tw, tl) >= 0.6
                refines = small and small <= big and len(big) - len(small) <= 1
                if (near or refines) and _shape_compat(agg[w], agg[l]):
                    _merge_into(agg, w, l)
                    log.append({"into": w, "merged": l,
                                "rule": "token-jaccard" if near else "token-subset"})
                    changed = True
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    ns = a.ns
    wo = f"projects/{a.project}/workflow-output"
    seg_dir = f"{wo}/segment"
    if not os.path.isdir(seg_dir):
        sys.exit(f"FAIL: {seg_dir} missing (run segment_probe first)")

    # Cluster-aware merge (ASSIST-PLAN B2 / protocol v2): only PASSING pages feed
    # the manifest — gatePass true (v1 stability or v2 consensus) or adjudicated
    # true (B6, green-by-adjudication). Non-passing pages are SKIPPED and logged,
    # never silently merged; the run-level verdict is segment-check.json's
    # majority gate, not this filter.
    segs = []
    skipped = []
    for fn in sorted(os.listdir(seg_dir)):
        if not fn.endswith(".segmentation.json"):
            continue
        s = json.load(open(os.path.join(seg_dir, fn)))
        if s.get("gatePass") is True or s.get("adjudicated") is True:
            segs.append(s)
        else:
            skipped.append(fn)
    for fn in skipped:
        print(f"  ! skipping non-passing segmentation: {fn}", file=sys.stderr)
    if not segs:
        sys.exit("FAIL: no passing segmentations")

    # detail templates (heuristic prior, vocabulary-independent)
    detail = {}
    try:
        tpl = json.load(open(f"{wo}/semantic-templates.json"))
        for dt in tpl.get("detailTemplates", []) or []:
            detail[dt["entityRole"]] = dt
    except Exception:
        pass

    # known heuristic candidate roles — the promotion vocabulary. Vision roots
    # rarely land on the EXACT element the heuristic altitude picked (outer
    # section vs inner items wrapper), so each vision component also claims the
    # candidate roles of its DESCENDANTS. Generic roles are excluded: promoting
    # 'div' would relabel unrelated regions site-wide.
    GENERIC_ROLES = {"div", "article", "section", "ul", "ol", "li",
                     "generic-container", "region--content"}
    candidate_roles = set()
    try:
        cand = json.load(open(f"{wo}/semantic-candidates.json"))
        for sec in ("components", "crossCutting", "nestedParts"):
            for c in cand.get(sec, []) or []:
                candidate_roles.add(c["role"])
    except Exception:
        pass
    candidate_roles -= GENERIC_ROLES

    frag_dir = f"{wo}/html-fragments"
    os.makedirs(frag_dir, exist_ok=True)

    agg = {}          # norm-name -> aggregate
    promote_roles = set()
    for s in segs:
        slug = s["slug"]
        dom_p = f"{seg_dir}/{slug}.dom.html"
        if not os.path.isfile(dom_p):
            print(f"  ! {slug}: dom.html missing — skipping field re-extraction", file=sys.stderr)
            continue
        soup = BeautifulSoup(open(dom_p, errors="replace").read(), "lxml")
        by_seg = {el.get("data-seg"): el for el in soup.find_all(attrs={"data-seg": True})}

        for comp in s.get("components", []):
            root = by_seg.get(str(comp.get("rootId")))
            if root is None:
                continue
            child_els = [by_seg.get(str(ch.get("rootId")))
                         for ch in (comp.get("children") or [])]
            child_els = [e for e in child_els if e is not None]
            comp_set = set(child_els)
            acc = SE.extract_fields(root, comp_set)
            shape = SE.shape_from_fields(acc)
            child_shape = None
            if child_els:
                cacc = SE.extract_fields(child_els[0], set())
                child_shape = SE.shape_from_fields(cacc)
            heur_role, _ = SE.role_and_variants(root, False)
            # descendant candidate roles — the cross-page promotion net
            sub_roles = set()
            if candidate_roles:
                for d in root.find_all(True):
                    if d.get("class"):
                        r_, _ = SE.role_and_variants(d, False)
                        if r_ in candidate_roles:
                            sub_roles.add(r_)
            key = norm_name(comp.get("name"))
            e = agg.setdefault(key, {
                "name": (comp.get("name") or key).strip(),
                "kind": comp.get("kind") or "component",
                "shapes": [], "childShapes": [], "heurRoles": set(),
                "pages": set(), "frequency": 0, "fragment": None,
                "interactive": False, "boxes": [],
            })
            e["shapes"].append(tuple(shape))
            if child_shape:
                e["childShapes"].append(tuple(child_shape))
            if heur_role not in GENERIC_ROLES:
                e["heurRoles"].add(heur_role)
            e["heurRoles"] |= sub_roles
            e["pages"].add(slug)
            e["frequency"] += 1
            e["interactive"] = e["interactive"] or bool(acc.get("interactive"))
            if e["fragment"] is None or len(str(root)) > len(e["fragment"][1]):
                e["fragment"] = (slug, str(root))
            if comp.get("box"):
                e["boxes"].append(comp["box"])

    # near-duplicate vision names collapse into one type each (merge log kept
    # in the manifest for pilot review); absorbed keys become aliases below.
    merge_log = consolidate_types(agg)
    for m in merge_log:
        print(f"  [consolidate] {m['merged']} -> {m['into']} ({m['rule']})")

    components, xcut = [], []
    instance_type_map = {}
    for key, e in sorted(agg.items(), key=lambda kv: -kv[1]["frequency"]):
        # dominant shape across instances
        from collections import Counter
        dom_shape = list(Counter(e["shapes"]).most_common(1)[0][0]) if e["shapes"] else []
        node = f"{ns}:{camel(key)}"
        # representative markup
        frag_rel = None
        if e["fragment"]:
            safe = re.sub(r"[^A-Za-z0-9._-]", "-", key)
            with open(f"{frag_dir}/{safe}.html", "w") as f:
                f.write(f"<!-- vision component: {e['name']} | page: {e['fragment'][0]} -->\n"
                        + e["fragment"][1])
            frag_rel = f"html-fragments/{safe}.html"
        if e["kind"] == "chrome":
            area = ("nav" if "nav" in key else
                    "footer" if "footer" in key else "header")
            xcut.append({"name": title_case(key), "nodeType": node, "area": area,
                         "fields": fields_from_shape(dom_shape), "coversRole": key,
                         "interactive": e["interactive"],
                         **({"htmlFragment": frag_rel} if frag_rel else {})})
            instance_type_map[key.lower()] = node
            for alias in e.get("aliases", ()):     # absorbed vision names
                instance_type_map.setdefault(alias.lower(), node)
            for hr in e["heurRoles"]:
                instance_type_map.setdefault(hr.lower(), node)
            continue
        child = None
        if e["kind"] == "container" and e["childShapes"]:
            cs = list(Counter(e["childShapes"]).most_common(1)[0][0])
            child = {"name": title_case(key) + " Item",
                     "nodeType": f"{ns}:{camel(key)}Item",
                     "fields": fields_from_shape(cs) or
                     [{"name": "title", "type": "string", "i18n": True, "mandatory": False}]}
        needs_mr = any(hr in detail for hr in e["heurRoles"])
        fields = fields_from_shape(dom_shape)
        # every skeleton component lifts its heading into jcr:title — the type
        # MUST carry mix:title (cnd_emit keys it on a 'title' field) or the
        # loader's jcr:title is silently skipped and the heading VANISHES from
        # the render (observed live: missing section h2)
        if not any(f["name"] == "title" for f in fields):
            fields.insert(0, {"name": "title", "type": "string",
                              "i18n": True, "mandatory": False})
        comp_entry = {
            "name": title_case(key),
            "nodeType": node,
            "coversRoles": sorted(e["heurRoles"]) + [key],
            "isContainer": e["kind"] == "container",
            "childType": child,
            "needsMainResource": needs_mr,
            "needsFullPage": needs_mr,
            "interactive": e["interactive"],
            "htmlFragments": {key: frag_rel} if frag_rel else {},
            "skeleton": True,          # promoted types render via skeleton views
            "layoutProperty": None,
            "views": [{"name": "default"}],
            "fields": fields,
            "frequency": e["frequency"],
            "pages": sorted(e["pages"]),
        }
        if needs_mr:
            dt = next(detail[hr] for hr in e["heurRoles"] if hr in detail)
            comp_entry["detailOf"] = dt.get("detailOf")
        components.append(comp_entry)
        instance_type_map[key.lower()] = node
        for alias in e.get("aliases", ()):         # absorbed vision names
            instance_type_map.setdefault(alias.lower(), node)
        for hr in e["heurRoles"]:
            instance_type_map.setdefault(hr.lower(), node)
            promote_roles.add(hr)
    instance_type_map["rawhtml"] = f"{ns}:rawHtml"

    manifest = {
        "generatedFrom": "segment2manifest.py (vision naming authority, deterministic re-extraction)",
        "crossCutting": xcut, "components": components, "templates": [],
        "typeCount": len(components), "instanceTypeMap": instance_type_map,
        "passthroughType": f"{ns}:rawHtml",
        "consolidation": merge_log,
    }
    v = naming_violations(manifest)
    manifest["namingViolations"] = v
    total = len(components) + len(xcut)
    manifest["namingQuality"] = ("good" if not v else
                                 "poor" if len(v) > max(2, total // 3) else "mixed")

    out = a.out or f"{wo}/component-manifest.json"
    with open(out, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    with open(f"{wo}/promote-roles.json", "w") as f:
        json.dump({"promoteRoles": sorted(promote_roles),
                   "_comment": "heuristic roles covered by vision components — "
                   "feed passthrough-overrides.json promoteRoles"}, f, indent=1)

    print(f"[segment2manifest] {out}: {len(components)} components, {len(xcut)} cross-cutting "
          f"from {len(segs)} segmented page(s); naming={manifest['namingQuality']}; "
          f"{len(promote_roles)} heuristic role(s) promotable")
    for c in components:
        print(f"  {c['nodeType']:30s} freq={c['frequency']:2d} covers={c['coversRoles']}"
              f"{' CONTAINER' if c['isContainer'] else ''}{' MAINRES' if c['needsMainResource'] else ''}")
    if v:
        for x in v[:6]:
            print(f"  [naming] ✗ {x['nodeType']}: {x['reason']}")


if __name__ == "__main__":
    main()
