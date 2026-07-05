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
import sys, os, json, re, hashlib, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup
import zone_detect as ZD
import semantic_extract as SE
import extract_content as EC

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# set per-project by build(): where extracted/looked-up assets live
MIRROR_ASSETS = STATIC_ASSETS = None
# hard per-prop budget: the loader truncates skeleton/skeletonOrig at 200k —
# a node whose markup exceeds CAP must be split, never silently truncated
CAP = 150_000
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
TEXT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "ul", "ol",
             "dl", "pre", "figcaption"}
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

_LAZY = re.compile(r'\sdata-(src|srcset|original|lazy-src|bg)=')
def materialize_lazy(html):
    """rule 30b: the crawl's below-fold images carry data-src (their JS swap never ran in
    a static server render) — promote data-src/data-srcset to real src/srcset so images show."""
    if not html or "data-" not in html:
        return html
    html = re.sub(r'\sdata-srcset=(["\'])', r' srcset=\1', html)
    html = re.sub(r'\sdata-(?:src|original|lazy-src)=(["\'])', r' src=\1', html)
    return html

_DATAURI = re.compile(
    r'src="data:image/(png|jpe?g|gif|webp|svg\+xml);base64,([A-Za-z0-9+/=]{4096,})"')

def extract_data_uris(html, base):
    """Inline base64 images -> real files under local-mirror/assets (DAM source) AND
    the module's static/assets (render source), src rewritten to the static URL.
    Measured need: one AEM carousel carried 3.74MB of base64 PNG inside a 3.79MB
    node — busting the loader's 200k prop cap AND defeating the DAM media lift."""
    if "data:image/" not in html:
        return html
    def repl(m):
        ext = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "gif": "gif",
               "webp": "webp", "svg+xml": "svg"}[m.group(1)]
        try:
            raw = base64.b64decode(m.group(2))
        except Exception:
            return m.group(0)
        name = "b64-" + hashlib.sha1(raw).hexdigest()[:16] + "." + ext
        for d in (MIRROR_ASSETS, STATIC_ASSETS):
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, name)
            if not os.path.exists(p):
                with open(p, "wb") as f:
                    f.write(raw)
        return f'src="{base}assets/{name}"'
    return _DATAURI.sub(repl, html)

def rw(html, base):
    return materialize_lazy(extract_data_uris(EC.rewrite_asset_refs(html, base), base))

def inst_weight(p):
    """Largest single prop this payload will write (loader truncates at 200k)."""
    w = max(len(p.get("skeleton") or ""), len(p.get("skeletonOrig") or ""))
    for ch in p.get("children") or []:
        w = max(w, len(ch.get("skeleton") or ""))
    return w

def emit_typed(el, lib, base):
    """A typed library instance with REAL lifted fields (G1: empty shells are the
    failure Julian rejected — every prop visible in Content Editor must carry the
    node's actual content). decompose_group places {{f:}}/{{media:}}/{{link:}}/
    {{child:}} markers on the source DOM and self-checks recompose == original
    byte-for-byte; on any miss this returns None and the caller falls back to
    verbatim rawHtml (rule 23: fidelity before contribution)."""
    html = rw(str(el), base)
    try:
        body = BeautifulSoup(html, "lxml").body
        root = body.find(True, recursive=False) if body else None
        d = SE.decompose_group(root, allow_items=(lib in CONTAINERS)) if root is not None else None
    except Exception as e:
        print(f"  ! decompose {lib}: {str(e)[:120]}", file=sys.stderr)
        d = None
    if not d or not d.get("ok"):
        return None
    def map_files(units):
        # DAM lift needs the mirror file: the rewritten src is /modules/<m>/static/
        # assets/<name> and the same <name> exists under local-mirror/assets
        for m in units or []:
            src = (m.get("src") or "").split("?", 1)[0]
            fn = os.path.basename(src)
            if fn and not src.startswith("data:") and MIRROR_ASSETS \
                    and os.path.isfile(os.path.join(MIRROR_ASSETS, fn)):
                m["file"] = fn
    map_files(d.get("media"))
    for ch in d.get("children") or []:
        map_files(ch.get("media"))
    return {"type": lib, "parent": None, "promoted": True,
            "skeleton": d["skeleton"], "skeletonOrig": d.get("original") or html,
            "fields": d.get("fields") or {},
            "media": d.get("media") or [], "mediaTotal": d.get("mediaTotal", 0),
            "link": d.get("link"), "linkTotal": d.get("linkTotal", 0),
            "children": d.get("children") or []}

def raw_inst(el, base, area=None):
    inst = {"type": "rawHtml", "parent": None, "passthrough": True,
            "fields": {"html": rw(str(el), base)}, "images": [], "links": []}
    if area:
        inst["area"] = area
    return inst

def build(project, site, ns, module=None):
    global MIRROR_ASSETS, STATIC_ASSETS
    MIRROR_ASSETS = f"{REPO}/projects/{project}/workflow-output/local-mirror/assets"
    STATIC_ASSETS = f"{REPO}/projects/{project}/static/assets"
    R = ZD.analyze(project)
    agg, isa, site_chrome = R["agg"], R["is_anchor"], R["site_chrome"]
    pages = ZD.load(project)
    stemdf = ZD.stem_docfreq([b for _, b in pages])
    module = module or project
    base = f"/modules/{module}/static/"
    stats = {"typed": 0, "wired": 0, "container": 0, "flatten": 0, "anon": 0,
             "textleaf": 0}
    try:
        EC.load_runtime_map(project)
    except Exception:
        pass
    # merge the localizer's FULL url->local-asset map (mirror.json urlMap, ~1600 entries incl.
    # /content/dam & /etc.clientlibs) so rewrite_asset_refs rewrites EVERY source asset ref to
    # the module-static copy. Without it only the ~2 runtime-manifest entries are covered and
    # 800+ property images stay as source /content/dam paths -> 404 -> broken images.
    try:
        mj = json.load(open(f"{REPO}/projects/{project}/workflow-output/local-mirror/mirror.json"))
        for k, v in mj.get("urlMap", {}).items():
            EC.RUNTIME_URL_MAP[k] = v
            # urlMap keys carry the host (//www.site.com/content/dam/…) but the markup refs
            # are host-relative (/content/dam/…) — register the host-stripped variant so the
            # substring rewrite matches. Both space and %20 forms of the path.
            m = re.match(r"^(?://|https?://)[^/]+(/.*)$", k)
            if m:
                rel = m.group(1)
                EC.RUNTIME_URL_MAP[rel] = v
                if " " in rel:
                    EC.RUNTIME_URL_MAP[rel.replace(" ", "%20")] = v
    except Exception:
        pass
    # Markup source = the LOCALISED mirror (local-mirror/<slug>.html), NOT the raw _crawl cache:
    # localize_site rewrote every asset ref to a LOCAL `assets/<hash>` path that rewrite_asset_refs
    # maps to /modules/<m>/static/assets (200). The raw crawl keeps the source's absolute
    # /content/dam/... paths (404 -> broken images). Structure is identical, so the detection
    # (scope/keys from analyze on _crawl) still applies. Shell also comes from the localised HTML.
    lm = f"{REPO}/projects/{project}/workflow-output/local-mirror"
    slug2raw, slug2body = {}, {}
    for slug, _ in pages:
        lp = os.path.join(lm, f"{slug}.html")
        if os.path.exists(lp):
            raw = open(lp, encoding="utf-8", errors="replace").read()
            slug2raw[slug] = raw
            b = BeautifulSoup(raw, "lxml").body
            if b is not None:
                slug2body[slug] = b

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

    def wired(p):
        return bool(p and (p["fields"] or p["media"] or p["link"] or p["children"]))

    def text_leaf_rich(el, html):
        """Bare text element (<h1>, <p>, <ul>…) decompose has nothing to lift from:
        ONE editable richText whose body IS the element — recompose is the identity
        ({{f:body}} splices body raw), fidelity exact by construction. These leaves
        (container-kid headings/intros) are what starved the G1 per-page floor
        (measured: leadership page 43%)."""
        try:
            tag = (el.name or "").lower()
        except Exception:
            return None
        if tag not in TEXT_TAGS or el.find(["img", "picture", "form", "script",
                                            "iframe", "svg", "video"]):
            return None
        if len(" ".join(el.get_text(" ", strip=True).split())) < 8:
            return None
        return {"type": "richText", "parent": None, "promoted": True,
                "skeleton": "{{f:body}}", "skeletonOrig": html,
                "fields": {"body": html}, "media": [], "link": None, "children": []}

    def lift_or_raw(el):
        """Anonymous block: still lift editable fields when the byte-exact decompose
        succeeds (generic `section` type) — text-leaf richText, then verbatim rawHtml
        otherwise. This carries the G1 per-page coverage floor on raw-heavy sites:
        a verbatim block is pixel-faithful but contributes 0 editable text."""
        t = emit_typed(el, "section", base)
        if t is not None and wired(t) and inst_weight(t) <= CAP:
            used.add("section")
            stats["anon"] += 1
            return t
        html = rw(str(el), base)
        t = text_leaf_rich(el, html)
        if t is not None and len(html) <= CAP:
            used.add("richText")
            stats["textleaf"] += 1
            return t
        return raw_inst(el, base)

    def wrapper_container(node):
        """Wrapper with typed/deep content -> ONE `section` container: its OWN markup
        with {{child:N}} replacing each annotate-kid subtree (string surgery on the
        rewritten markup — recompose is substring re-insertion, byte-exact by
        construction). Children are emitted as parent-linked instances, so the
        wrapper markup is PRESERVED: the v1 flatten-descend dropped it and collapsed
        CSS-grid layouts (measured: destinations 23.8% ground truth)."""
        W = rw(str(node["_el"]), base)
        parts = [rw(str(kd["_el"]), base) for kd in node["kids"]]
        skel, rest, ok = "", W, True
        for n, p in enumerate(parts):
            i = rest.find(p)
            if i < 0:
                ok = False
                break
            skel += rest[:i] + "{{child:%d}}" % n
            rest = rest[i + len(p):]
        skel += rest
        if not ok or len(skel) > CAP:
            return None
        # no skeletonOrig on containers: the skeleton is exact by construction and
        # duplicating the whole subtree per nesting level would explode the payload
        return {"type": "section", "parent": None, "promoted": True,
                "skeleton": skel, "fields": {}, "media": [], "link": None,
                "children": []}

    def emit_node(node, insts, depth, parent=None):
        """Emit ONE annotate node, recursively, as parent-linked instances.
        Inside a container (parent is not None) every node emits EXACTLY ONE
        direct child instance — the {{child:N}} markers splice JCR children by
        ORDER, so the one-instance-per-kid contract is what keeps the container
        recomposition aligned."""
        k = node["key"]
        lib, conf, sc = lib_of(node)
        if parent is None:
            # chrome: emit each DISTINCT chrome block once (dedup by key), routed to
            # a template AbsoluteArea (header/nav/footer); prune the subtree
            if k and (k in site_chrome or sc == "ABSOLUTE"):
                if k not in chrome_done:
                    chrome_done.add(k)
                    chrome.append(raw_inst(node["_el"], base, area_for(k)))
                return
            if k and R["is_root_wrapper"](k):
                for kd in node["kids"]:  # transparent layout root (top level only)
                    emit_node(kd, insts, depth, parent)
                return
        if lib and conf >= 0.5 and lib in ZD.LIBRARY_TYPES:
            t = emit_typed(node["_el"], lib, base)
            # a typed node that lifts NOTHING is exactly G1's "empty shell"
            # (typed façade, zero editable content) — demote it (rule 23)
            if t is not None and wired(t) and inst_weight(t) <= CAP:
                t["parent"] = parent
                insts.append(t)
                used.add(lib)
                stats["typed"] += 1
                stats["wired"] += 1
                return  # prune at the first confident anchor (maximal typed component)
        too_big = node["size"] > 300 or len(str(node["_el"])) > CAP
        if depth < 10 and node["kids"] and (subtree_has_typed(node) or too_big):
            w = wrapper_container(node)
            if w is not None:
                w["parent"] = parent
                idx = len(insts)
                insts.append(w)
                used.add("section")
                stats["container"] += 1
                for kd in node["kids"]:
                    emit_node(kd, insts, depth + 1, idx)
                return
            if parent is None:
                # wrapper markup not substring-splittable: flatten — loses the
                # wrapper (counted, never silent); forbidden inside containers
                # (it would break the one-instance-per-marker contract)
                stats["flatten"] += 1
                for kd in node["kids"]:
                    emit_node(kd, insts, depth + 1, parent)
                return
        if too_big:  # no silent caps: an irreducible over-cap leaf is REPORTED
            print(f"  ! irreducible verbatim leaf over cap: {len(str(node['_el']))} chars "
                  f"(key={k})", file=sys.stderr)
        t = lift_or_raw(node["_el"])
        t["parent"] = parent
        insts.append(t)

    max_zones = 0
    for slug, crawl_body in pages:
        body = slug2body.get(slug, crawl_body)  # prefer localised markup (local asset refs)
        ann = ZD.annotate(body, stemdf, keep_el=True)
        root = content_root(ann, site_chrome)
        insts = []
        # C1 zones: each top-level band (content-root direct child) routes its
        # top-level instances to its own template zone Area (z1..zK) — several
        # non-absolute contribution zones per page; zone order = document order
        band = 0
        for kid in root["kids"]:
            start = len(insts)
            emit_node(kid, insts, 0, None)
            tops = [i for i in insts[start:]
                    if i.get("parent") is None and not i.get("area")]
            if tops:
                band += 1
                for i in tops:
                    i["zone"] = f"z{band}"
        max_zones = max(max_zones, band)
        if not insts:  # never emit an empty page
            insts.append(raw_inst(root["_el"], base))
        shell = None
        if slug in slug2raw:
            try:
                shell = EC.page_shell(materialize_lazy(slug2raw[slug]), base)
            except Exception:
                shell = None
        if shell is not None:
            # zone shells carry no chrome markup (levels stop at body) — the
            # Layout must keep rendering the contributed AbsoluteAreas (C0b)
            shell["chromeAreas"] = True
        out[slug] = {"adapter": "semantic", "instances": insts, "shell": shell}

    if chrome and out:
        first = next(iter(out))
        # prepending chrome SHIFTS every instance index on the first page —
        # parent refs must shift too, or children nest under the wrong nodes
        # (caught live by the C0a gate: en/home failures + silent mis-nesting)
        off = len(chrome)
        for i in out[first]["instances"]:
            if i.get("parent") is not None:
                i["parent"] += off
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
                "components": comps, "zones": max_zones,
                "crossCutting": [{"coversRole": a, "nodeType": f"{ns}:rawHtml", "area": a}
                                 for a in chrome_areas]}
    return content, manifest, used, stats

def stamp_zones(module_dir, k):
    """Rewrite the module's basic.server.tsx zone block: <Area name=z1..zK> in
    document order + the main fallback Area. Idempotent (zones:start/end markers;
    first stamp anchors on the bare main Area)."""
    p = os.path.join(module_dir, "src", "templates", "Page", "basic.server.tsx")
    if not os.path.exists(p):
        print(f"  ! stamp_zones: {p} missing", file=sys.stderr)
        return
    src = open(p).read()
    areas = "\n".join(f'        <Area name="z{i + 1}" />' for i in range(k))
    block = ("{/* zones:start */}\n" + areas +
             '\n        <Area name="main" />\n        {/* zones:end */}')
    new, n = re.subn(r"\{/\* zones:start \*/\}[\s\S]*?\{/\* zones:end \*/\}", block, src)
    if not n:
        new, n = re.subn(r'<Area name="main" />', block, src, count=1)
    if n:
        open(p, "w").write(new)
        print(f"  -> {k} zone Areas stamped in {p}")
    else:
        print(f"  ! stamp_zones: no anchor in {p}", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: zone_to_contentload.py <project> [<site>] [--ns asr]")
    project = sys.argv[1]
    site = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else project
    ns = "asr"
    if "--ns" in sys.argv:
        ns = sys.argv[sys.argv.index("--ns") + 1]
    module = sys.argv[sys.argv.index("--module") + 1] if "--module" in sys.argv else None
    content, manifest, used, stats = build(project, site, ns, module)
    cl_path = os.path.join(REPO, "orchestration", "content", f"{project}.content-load.json")
    mf_dir = os.path.join(REPO, "projects", project, "workflow-output")
    os.makedirs(mf_dir, exist_ok=True)
    mf_path = os.path.join(mf_dir, "component-manifest.json")
    json.dump(content, open(cl_path, "w"), ensure_ascii=False, indent=1)
    json.dump(manifest, open(mf_path, "w"), ensure_ascii=False, indent=1)
    # stamp_zones targets the PROJECT dir (source files live in projects/<project>),
    # NOT the module bundle name (which only shapes the /modules/<module>/ asset URL)
    stamp_zones(os.path.join(REPO, "projects", project), manifest["zones"])
    npages = len(content["pages"])
    ninst = sum(len(p["instances"]) for p in content["pages"].values())
    ntyped = sum(1 for p in content["pages"].values() for i in p["instances"]
                 if i["type"] != "rawHtml")
    nmedia = sum(len(i.get("media") or []) for p in content["pages"].values()
                 for i in p["instances"])
    nlink = sum(1 for p in content["pages"].values() for i in p["instances"]
                if i.get("link"))
    nkids = sum(len(i.get("children") or []) for p in content["pages"].values()
                for i in p["instances"])
    print(f"{project}: {npages} pages | {ninst} instances | {ntyped} typed ({100*ntyped/max(ninst,1):.0f}%) | "
          f"library types: {sorted(used)}")
    nzones = manifest.get("zones", 0)
    print(f"  contribution: wired {stats['wired']}/{stats['typed']} typed "
          f"({100*stats['wired']/max(stats['typed'],1):.0f}%) | anon-lift {stats['anon']} | "
          f"text-leaf {stats['textleaf']} | containers {stats['container']} "
          f"(flatten {stats['flatten']}) | media units {nmedia} | links {nlink} | "
          f"item children {nkids} | zones z1..z{nzones}")
    print(f"  -> {cl_path}")
    print(f"  -> {mf_path}")

if __name__ == "__main__":
    main()
