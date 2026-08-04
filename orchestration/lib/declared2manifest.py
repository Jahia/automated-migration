#!/usr/bin/env python3
"""declared2manifest.py — the archetype manifest from the source's OWN declaration.

The DECLARED ARM of the component-model phase. `segment2manifest` derives the
manifest from vision segmentation, which is the right tool for a source that hides
its structure. When a source's CMS DECLARES its components in the rendered DOM
(Sitecore SXA `div.component <type>` + `field-<name>`, Drupal `paragraph--type-*`,
an explicit `data-component`), paying for vision buys nothing the declaration does
not already give — deterministically, completely, and in seconds.

Measured (2026-08-03, lesalondelaphoto.com, 27 pages, Qwen3.5-9B):
  vision arm    ~7h projected, 0 of 27 pages green — consensus agreement
                0.556-0.778 against the frozen 0.8 bar, and the home page's medoid
                run returned ONE component with zero containers for a 12-band page
  declared arm  36 declared types with fields + containers, and
                `extract_content --adapter sxa` produced 556 per-page instances
                with 121k chars of real field text in under 3 minutes

Emits the SAME manifest contract segment2manifest emits (model=archetype,
components + crossCutting, instanceTypeMap, passthroughType), so every downstream
producer — cnd_emit, install_shell_templates, semanticize_content, load_content —
is untouched. It also emits `sxaSource` per component and a top-level `sxaIgnored`,
which makes `probes/sxa-coverage.sh` the arm's completeness gate: every declared
type is mapped or explicitly ignored, never silently dropped.

Type mapping, in order of authority:
  1. the REVIEWED component model (`component-model.json` types[].._sxaSource) —
     the operator-approved decision wins over any heuristic;
  2. `archetypes.classify_region` on the declared type name + its container shape;
  3. declared types listed in the model's `sxaIgnored` map to the passthrough type.

Usage: declared2manifest.py <project> --ns sdp [--mixns sdpmix] [--out PATH]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archetypes as ARCH                                          # noqa: E402

# always shipped, whatever the source declares (rule 19 + "every module ships
# these"): the tree-driven nav and the editor's listing/layout tools
ALWAYS = ("mainNavigation", "subNavigation", "jcrQuery", "cols", "section")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", required=True)
    ap.add_argument("--mixns")
    ap.add_argument("--out")
    a = ap.parse_args()
    p, ns = a.project, a.ns
    mixns = a.mixns or f"{ns}mix"
    pp = f"projects/{p}"
    wo = f"{pp}/workflow-output"

    dpath = f"{pp}/.reference/declared-components.json"
    if not os.path.exists(dpath):
        dpath = f"{pp}/.reference/sxa-components.json"
    try:
        decl = json.load(open(dpath))
    except (OSError, ValueError) as e:
        sys.exit(f"FAIL declared2manifest: no declared inventory ({e}) — run "
                 f"orchestration/lib/declared_inventory.py {p} first")
    types = decl.get("components") or []
    if not types:
        sys.exit(f"FAIL declared2manifest: {dpath} declares 0 component types — this "
                 f"source has no declaration to build from; use the vision arm")

    # the REVIEWED model is the authority when it exists
    model_map, ignored = {}, set()
    mp = f"{wo}/component-model.json"
    if os.path.exists(mp):
        model = json.load(open(mp))
        rev = {ARCH.node_local(k): k for k in ARCH.ARCHETYPES}
        for nt, spec in (model.get("types") or {}).items():
            akey = rev.get(nt.split(":")[-1])
            if not akey:
                continue
            for src in spec.get("_sxaSource") or []:
                model_map[str(src).lower()] = akey
        for row in model.get("sxaIgnored") or []:
            ignored.add(str(row.get("type") if isinstance(row, dict) else row).lower())
        print(f"  ~ reviewed model: {len(model_map)} declared type(s) mapped by "
              f"decision, {len(ignored)} ignored", file=sys.stderr)

    # CHILD vs BAND, from the source's own two signals (no guessing): the
    # declaration records CONTAINMENT (`carousel` contains `Slide`), and the census
    # records the TOP-LEVEL band vocabulary. A declared type that is someone's child
    # and never appears as a top-level band is that container's ITEM — it must map to
    # the parent archetype's childType (Slide -> ns:cardItem), not mint a band type of
    # its own. Measured: without this, `Slide` classified as a richTextSection band,
    # putting carousel slides beside the carousel instead of inside it.
    child_of = {}
    for t in types:
        for ch in t.get("childTypes") or []:
            child_of.setdefault(str(ch).lower(), set()).add(t["type"].lower())
    top_bands = set()
    try:
        cen = json.load(open(f"{wo}/model-census.json"))
        top_bands = {str(r.get("band", "")).lower() for r in (cen.get("bandTypes") or [])}
    except (OSError, ValueError):
        print("  ~ no model-census.json — child/band routing falls back to the "
              "classifier alone", file=sys.stderr)

    passthrough = f"{ns}:rawHtml"
    by_arch, itm, low, mapped_ignored, child_routed = {}, {}, [], [], []
    for t in types:
        name = t["type"]
        key = name.lower()
        aliases = [str(x).lower() for x in (t.get("aliases") or [])]
        if key in ignored:
            mapped_ignored.append(name)
            itm[key] = passthrough
            for al in aliases:
                itm.setdefault(al, passthrough)
            continue
        akey = model_map.get(key)
        source = "model"
        if not akey and key in child_of and key not in top_bands:
            # route to the parent's childType — the declaration says it is an item
            parent_akey = next((model_map.get(pk)
                                or ARCH.classify_region(
                                    pk, kind="component",
                                    is_container=True)[0]
                                for pk in sorted(child_of[key])), None)
            child = (ARCH.ARCHETYPES.get(parent_akey) or {}).get("child")
            if child:
                cnode = f"{ns}:{child['key']}"
                itm[key] = cnode
                for al in aliases:
                    itm.setdefault(al, cnode)
                child_routed.append(f"{name} -> {cnode} (item of {parent_akey})")
                # it is accounted FOR by its container: record it on the parent's
                # sxaSource so the coverage gate sees a modelled type, not a drop
                by_arch.setdefault(parent_akey, {"covers": set(), "declared": set(),
                                                 "freq": 0, "pages": set(),
                                                 "bySource": set()})
                by_arch[parent_akey]["declared"].add(name)
                by_arch[parent_akey]["bySource"].add("declared-child")
                continue
        if not akey:
            akey, conf = ARCH.classify_region(name, kind="component",
                                              is_container=bool(t.get("isContainer")))
            source = "classifier"
            if conf == "low":
                low.append(name)
        b = by_arch.setdefault(akey, {"covers": set(), "declared": set(), "freq": 0,
                                      "pages": set(), "bySource": set()})
        b["covers"].add(key)
        b["covers"].update(aliases)
        b["declared"].add(name)
        b["freq"] += int(t.get("instances") or 0)
        b["pages"].update(t.get("pages") or [])
        b["bySource"].add(source)
        node = f"{ns}:{ARCH.node_local(akey)}"
        itm[key] = node
        for al in aliases:
            itm.setdefault(al, node)

    components, xcut = [], []
    for akey, b in sorted(by_arch.items(), key=lambda kv: -kv[1]["freq"]):
        comp = ARCH.to_manifest_component(akey, ns, mixns,
                                          covers_roles=sorted(b["covers"]))
        comp["frequency"] = b["freq"]
        comp["pages"] = sorted(b["pages"])[:24]
        # the coverage contract sxa-coverage.sh gates on
        comp["sxaSource"] = sorted(b["declared"])
        comp["mappedBy"] = sorted(b["bySource"])
        itm.setdefault(akey.lower(), comp["nodeType"])
        if comp.get("chrome"):
            comp["area"] = comp["chrome"]
            xcut.append(comp)
        else:
            components.append(comp)

    # ENTITY TYPES come from the ENTITY MAP, not from declared bands (2026-08-03).
    # A declared source describes the components a PAGE is built from; jmix:mainResource
    # types describe content that is not a page at all, so nothing in the declaration
    # names them. Without this the CND shipped no newsArticle / event / directoryEntry
    # and every load_main_resources create would fail on an unknown node type.
    present = {c["nodeType"] for c in components} | {c["nodeType"] for c in xcut}
    rev_local = {ARCH.node_local(k): k for k in ARCH.ARCHETYPES}
    entity_types = []
    try:
        _mr = json.load(open(f"orchestration/content/{p}.mainresource.json"))
        for fkey, f in (_mr.get("folders") or {}).items():
            nt = f.get("type") or ""
            akey = rev_local.get(nt.split(":")[-1])
            if not akey or f"{ns}:{ARCH.node_local(akey)}" in present:
                continue
            comp = ARCH.to_manifest_component(akey, ns, mixns)
            comp["frequency"] = 0
            comp["pages"] = []
            comp["sxaSource"] = []
            comp["fromEntityMap"] = sorted(
                k for k, v in (_mr.get("folders") or {}).items()
                if (v.get("type") or "") == nt)
            components.append(comp)
            present.add(comp["nodeType"])
            entity_types.append(comp["nodeType"])
            itm.setdefault(akey.lower(), comp["nodeType"])
    except (OSError, ValueError):
        pass

    for akey in ALWAYS:
        node = f"{ns}:{ARCH.node_local(akey)}"
        if node in present:
            continue
        comp = ARCH.to_manifest_component(akey, ns, mixns)
        comp["frequency"] = 0
        comp["pages"] = []
        comp["standard"] = True
        comp["sxaSource"] = []
        if comp.get("chrome"):
            comp["area"] = comp["chrome"]
            xcut.append(comp)
        else:
            components.append(comp)
        itm.setdefault(akey.lower(), node)
    itm["rawhtml"] = passthrough

    manifest = {
        "generatedFrom": ("declared2manifest.py (SOURCE DECLARATION authority — the "
                          f"CMS adapter '{decl.get('adapter', 'unknown')}' declares "
                          "component boundaries + fields in the DOM; no vision spend)"),
        "model": "archetype",
        "mixns": mixns,
        "crossCutting": xcut,
        "components": components,
        "templates": [],
        "typeCount": len(components),
        "instanceTypeMap": itm,
        "passthroughType": passthrough,
        "consolidation": {},
        "namingViolations": [],      # archetype library names, clean by construction
        "namingQuality": "good",
        "sxaIgnored": sorted(mapped_ignored),
        "entityTypes": sorted(entity_types),
        "childRouted": sorted(child_routed),
        "declaredCoverage": {"declaredTypes": len(types),
                             "mapped": len(types) - len(mapped_ignored),
                             "ignored": len(mapped_ignored),
                             "byDecision": sum(1 for t in types
                                               if t["type"].lower() in model_map),
                             "byClassifier": sum(1 for t in types
                                                 if t["type"].lower() not in model_map
                                                 and t["type"].lower() not in ignored)},
    }
    out = a.out or f"{wo}/component-manifest.json"
    json.dump(manifest, open(out, "w"), indent=2, ensure_ascii=False)
    dc = manifest["declaredCoverage"]
    print(f"declared2manifest: {dc['declaredTypes']} declared type(s) -> "
          f"{len(components)} component type(s) + {len(xcut)} chrome type(s) "
          f"({dc['byDecision']} by reviewed decision, {dc['byClassifier']} by "
          f"classifier, {dc['ignored']} ignored) -> {out}")
    for c in sorted(components + xcut, key=lambda c: -c.get("frequency", 0))[:14]:
        print(f"  x{c.get('frequency', 0):<5} {c['nodeType']:<24} "
              f"<- {', '.join(c.get('sxaSource') or ['(standard tool)'])[:60]}")
    if entity_types:
        print(f"  ~ entity types from the entity map: {', '.join(entity_types)}")
    for cr in child_routed:
        print(f"  ~ item: {cr}")
    if low:
        print(f"  ! {len(low)} declared type(s) mapped by the classifier with LOW "
              f"confidence — decide them in the model: {', '.join(low[:8])}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
