#!/usr/bin/env python3
"""
zone_to_contentload — emit content-load.json + component-manifest.json from the fine-signal
zone_detect model. The `--segmentation zone` sibling of extract_content's vision/semantic
adapters: zone_detect makes the BOUNDARY decision (scope + library_map), this recovers the
markup and delegates the field-lift to semantic_extract.decompose_group.

Emission (fidelity-first, everything covered):
  - walk the content root; DESCEND unrecognised wrapper blocks to find typed components;
  - a block whose identity maps to a library type (conf>=0.5) -> that type, with the lifted
    skeleton (fields/{{markers}}/child items) AND a verbatim `skeletonOrig` (byte-exact
    outerHTML) so the view renders byte-identical until an editor fills the typed fields;
  - everything else -> verbatim `rawHtml` passthrough (nothing dropped);
  - ABSOLUTE chrome (header/footer/nav) -> `area`-tagged instance, emitted once per site.
Containers carry decomposed `children` (item nodes) + a manifest `childType`. EDIT-only; the
loader never publishes. Media DAM-weakref lift is deferred (images render verbatim via
skeletonOrig) — a follow-up; fidelity holds by construction.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zone_detect as ZD
import semantic_extract as SE
import extract_content as EC

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AREA = {"role:banner": "header", "tag:header": "header", "role:contentinfo": "footer",
        "tag:footer": "footer", "role:navigation": "nav", "tag:nav": "nav"}

def area_for(key):
    """Route a chrome anchor to a template AbsoluteArea (header/nav/footer). Landmark/semantic
    keys map exactly; class-based chrome (sites without ARIA landmarks, e.g. AEM) routes by name."""
    if key in AREA:
        return AREA[key]
    k = key.split(":", 1)[-1].lower()
    if "footer" in k or "contentinfo" in k:
        return "footer"
    if ("nav" in k or "menu" in k) and "footer" not in k:
        return "nav"
    return "header"  # top-bar, header, search, dialog, chatbot, announcement, booking …
CONTAINERS = {"section", "gridRow", "cardGrid", "logoWall", "carousel", "tabs", "accordion"}
CHILD_TYPE = {"carousel": "card", "logoWall": "logo", "tabs": "tab", "cardGrid": "card",
              "accordion": "faqItem", "section": "card", "gridRow": "card"}

def content_root(node, chrome):
    n = node
    while True:
        live = [k for k in n["kids"] if k["key"] not in chrome]
        if len(live) == 1 and live[0]["size"] >= 0.6 * n["size"]:
            n = live[0]
        else:
            break
    return n

def rw(html, base):
    return EC.rewrite_asset_refs(html, base)

def emit_typed(el, lib, base):
    """A typed library instance carrying its byte-exact source markup in `skeletonOrig`
    (rendered verbatim by the universal <Verbatim> view fallback). MVP scope: the node is
    TYPED (modular tree: editor sees Card/Carousel/… ) + fidelity-safe by construction. Field-
    level lifting (skeleton markers + contribBody/media/link mixins) is the documented follow-up;
    keeping the MVP to skeletonOrig-only avoids the per-type CND-schema coupling and the loader's
    always-set `skeleton` constraint, so any base-library type loads cleanly."""
    return {"type": lib, "parent": None, "promoted": True,
            "skeletonOrig": rw(str(el), base), "fields": {}, "images": [], "links": []}

def raw_inst(el, base, area=None):
    inst = {"type": "rawHtml", "parent": None, "passthrough": True,
            "fields": {"html": rw(str(el), base)}, "images": [], "links": []}
    if area:
        inst["area"] = area
    return inst

def build(project, site, ns, module=None):
    R = ZD.analyze(project)
    agg, isa, site_chrome = R["agg"], R["is_anchor"], R["site_chrome"]
    pages = ZD.load(project)
    stemdf = ZD.stem_docfreq([b for _, b in pages])
    module = module or project
    base = f"/modules/{module}/static/"
    try:
        EC.load_runtime_map(project)
    except Exception:
        pass

    used, out, chrome, chrome_done = set(), {}, [], set()

    def lib_of(node):
        k = node["key"]
        if not k or not isa(k):
            return (None, 0.0, None)
        e = agg.get(k, {})
        sc = e.get("scope")
        lib, conf = ZD.library_map(k, node["tier"], sc or "COMPONENT", e.get("sib", 0), bool(node["kids"]))
        return (lib, conf, sc)

    def is_typed(node):
        lib, conf, _ = lib_of(node)
        return bool(lib and conf >= 0.5 and lib in ZD.LIBRARY_TYPES)

    def subtree_has_typed(node):
        for d in node["kids"]:
            if is_typed(d) or subtree_has_typed(d):
                return True
        return False

    def emit_blocks(node, insts, depth):
        for child in node["kids"]:
            k = child["key"]
            lib, conf, sc = lib_of(child)
            # chrome: emit each DISTINCT chrome block once (dedup by key), routed to a template
            # AbsoluteArea (header/nav/footer) so it renders on every page; then prune the subtree
            if k and (k in site_chrome or sc == "ABSOLUTE"):
                if k not in chrome_done:
                    chrome_done.add(k)
                    chrome.append(raw_inst(child["_el"], base, area_for(k)))
                continue
            if k and R["is_root_wrapper"](k):
                emit_blocks(child, insts, depth)  # transparent layout root
                continue
            if lib and conf >= 0.5 and lib in ZD.LIBRARY_TYPES:
                insts.append(emit_typed(child["_el"], lib, base))
                used.add(lib)
                continue  # prune at the first confident anchor (maximal typed component)
            # unrecognised wrapper: descend to reach typed components deeper (incl. single-child
            # wrappers), OR to split a very large block so no single verbatim node exceeds the
            # loader's 200k skeleton cap (fidelity: avoid truncating a huge blob). Emit verbatim
            # only for a small opaque block with nothing typed inside.
            too_big = child["size"] > 300 or len(str(child["_el"])) > 120_000
            if depth < 10 and (subtree_has_typed(child) or too_big) and child["kids"]:
                emit_blocks(child, insts, depth + 1)
            else:
                insts.append(raw_inst(child["_el"], base))

    for slug, body in pages:
        ann = ZD.annotate(body, stemdf, keep_el=True)
        root = content_root(ann, site_chrome)
        insts = []
        emit_blocks(root, insts, 0)
        if not insts:  # never emit an empty page
            insts.append(raw_inst(root["_el"], base))
        out[slug] = {"adapter": "semantic", "instances": insts}

    if chrome and out:
        first = next(iter(out))
        out[first]["instances"] = chrome + out[first]["instances"]

    content = {"adapter": "semantic", "pages": out}
    # loader looks up type_map[inst["type"].lower()] (load_content.py:862) — keys MUST be lowercased
    # ("cardGrid" -> "cardgrid") or the instance is silently skipped as an unmapped helper.
    itm = {lib.lower(): f"{ns}:{lib}" for lib in used}
    itm["rawhtml"] = f"{ns}:rawHtml"
    comps = []
    for lib in sorted(used):
        c = {"nodeType": f"{ns}:{lib}"}
        if lib in CONTAINERS:
            c["isContainer"] = True
            c["childType"] = {"nodeType": f"{ns}:{CHILD_TYPE.get(lib, 'card')}"}
        comps.append(c)
    chrome_areas = sorted({c["area"] for c in chrome})
    manifest = {"instanceTypeMap": itm, "passthroughType": f"{ns}:rawHtml",
                "components": comps,
                "crossCutting": [{"coversRole": a, "nodeType": f"{ns}:rawHtml", "area": a}
                                 for a in chrome_areas]}
    return content, manifest, used

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: zone_to_contentload.py <project> [<site>] [--ns asr]")
    project = sys.argv[1]
    site = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else project
    ns = "asr"
    if "--ns" in sys.argv:
        ns = sys.argv[sys.argv.index("--ns") + 1]
    module = sys.argv[sys.argv.index("--module") + 1] if "--module" in sys.argv else None
    content, manifest, used = build(project, site, ns, module)
    cl_path = os.path.join(REPO, "orchestration", "content", f"{project}.content-load.json")
    mf_dir = os.path.join(REPO, "projects", project, "workflow-output")
    os.makedirs(mf_dir, exist_ok=True)
    mf_path = os.path.join(mf_dir, "component-manifest.json")
    json.dump(content, open(cl_path, "w"), ensure_ascii=False, indent=1)
    json.dump(manifest, open(mf_path, "w"), ensure_ascii=False, indent=1)
    npages = len(content["pages"])
    ninst = sum(len(p["instances"]) for p in content["pages"].values())
    ntyped = sum(1 for p in content["pages"].values() for i in p["instances"]
                 if i["type"] != "rawHtml")
    print(f"{project}: {npages} pages | {ninst} instances | {ntyped} typed ({100*ntyped/max(ninst,1):.0f}%) | "
          f"library types: {sorted(used)}")
    print(f"  -> {cl_path}")
    print(f"  -> {mf_path}")

if __name__ == "__main__":
    main()
