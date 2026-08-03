#!/usr/bin/env python3
"""
zone_detect — FINE-SIGNAL-FIRST zone/component identification for the migration pipeline.
Generic, analysis-only (zero Jahia). Promoted from the P6.4 spike (validated on 5 corpora,
adversarially verified). See orchestration/ZONE-DETECTION-APPROACH.md.

Public API: analyze(project) -> R (model) · emit_json(R, path) · library_map(key,...) -> (type, conf)
· regime(R) · scaling(project). CLI: `python zone_detect.py <project> [--scaling]`.

Signal hierarchy (determinism decreasing); the STRUCTURAL hash is now a fallback, not primary:
  L0  explicit content-model markers: data-component / data-testid / itemtype        (identity given)
  L1  ARIA landmark role / HTML5 semantic tag: banner/contentinfo/nav/main/article   (scope given)
  L2  framework class stem: cmp- / field- / paragraph--/ block- / lfr- / component-  (component id)
  L3  recurring semantic class stem (dehashed, util-filtered, doc-freq>=3)           (component id)
  L4  structural tag-shape hash                                                       (anonymous fallback)

Generic mechanism (site-agnostic): a normalized non-utility class stem / marker that RECURS is a
component identity; DOM nesting gives containment (zone -> component -> sub-component); repeated
same-key siblings are RECORDS. Framework prefixes are a confidence prior, never required.

Scope (relativised to template cluster): landmark/site-wide -> ABSOLUTE ZONE; ~all pages of one
template -> TEMPLATE ZONE; per-instance -> COMPONENT; sibling-repeat -> RECORD.
"""
import sys, os, json, re, hashlib, statistics
from collections import defaultdict, Counter
from bs4 import BeautifulSoup, Comment

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance  # stamps the emit_json output

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DROP = {"script", "style", "noscript", "template", "link", "meta", "br", "wbr", "source", "svg",
        "path", "iframe", "canvas"}
LANDMARK = {"banner", "contentinfo", "navigation", "main", "complementary", "search",
            "form", "dialog", "tablist", "tabpanel", "region"}
SEMTAG = {"header", "footer", "nav", "main", "article", "aside"}
FW_PREFIX = ("cmp-", "cmp_", "field-", "field--name-", "paragraph--type-", "block-", "lfr-",
             "osb-", "sxa-", "component", "hero", "teaser", "card", "carousel", "accordion",
             "slider", "banner", "testimonial", "cta", "breadcrumb")
UTIL_PREFIX = ("col-", "col", "row", "d-", "flex", "bg-", "text-", "mt-", "mb-", "ms-", "me-",
    "ps-", "pe-", "px-", "py-", "pt-", "pb-", "p-", "m-", "mx-", "my-", "w-", "h-", "g-", "gap-",
    "justify-", "align-", "order-", "rounded", "border", "shadow", "container", "position-",
    "fa-", "fas", "far", "fab", "offset-", "gx-", "gy-", "d-flex")
UTIL_EXACT = {"odd", "even", "wrap", "active", "disabled", "hidden", "show", "hide", "clearfix",
    "sr-only", "visually-hidden", "no-gutters", "img-fluid", "float-start", "float-end", "fw-bold",
    "fw-normal", "small", "large", "center", "left", "right", "clear", "first", "last",
    # positional / display / framework-plumbing utilities (verification: these leaked as identities)
    "absolute", "relative", "fixed", "sticky", "static", "display-none", "d-block", "d-inline",
    "root", "responsivegrid", "rah-static", "aos-init", "aos-animate", "swiper-initialized",
    "in", "out", "open", "close", "collapse", "collapsed", "expanded", "selected", "block", "inline"}

HASHSUF = re.compile(r"__[A-Za-z0-9]{2,8}_?$")
def stem(tok):
    m = HASHSUF.search(tok)
    if m and re.search(r"[A-Z0-9]", m.group(0)):
        return tok[:m.start()]
    return tok
TW_VARIANT = ("sm:", "md:", "lg:", "xl:", "2xl:", "hover:", "focus:", "group-", "peer-",
              "col-span", "grid-cols", "space-", "gap", "inset-", "top-", "bottom-", "left-",
              "right-", "z-", "opacity-", "leading-", "tracking-", "font-", "items-", "self-")
def is_util(t):
    if ":" in t:  # Tailwind responsive/state variant classes are always styling
        return True
    return t in UTIL_EXACT or any(t == p or t.startswith(p) for p in UTIL_PREFIX + TW_VARIANT)
def is_fw(t):
    return any(t.startswith(p) for p in FW_PREFIX)
def norm_val(v):
    return re.sub(r"[_\-\s]?\d+$", "", str(v).strip().lower())

def identity(tag, attrs, stemdf):
    for a in ("data-component", "data-testid", "data-widget", "data-block", "data-qa"):
        v = attrs.get(a)
        if v:
            return ("cmp:" + norm_val(v), "L0")
    it = attrs.get("itemtype")
    if it:
        return ("type:" + it.rstrip("/").rsplit("/", 1)[-1].lower(), "L0")
    role = attrs.get("role")
    if role in LANDMARK:
        return ("role:" + role, "L1")
    if tag in SEMTAG:
        return ("tag:" + tag, "L1")
    cls = [stem(c.strip()) for c in (attrs.get("class") or [])]
    cls = [c for c in cls if c and not is_util(c)]
    fw = [c for c in cls if is_fw(c)]
    if fw:
        return ("cls:" + min(fw, key=len), "L2")
    rec = [c for c in cls if stemdf.get(c, 0) >= 3]
    if rec:
        return ("cls:" + max(rec, key=lambda c: stemdf[c]), "L3")
    return (None, None)

# ---- pass 1: class-stem document frequency ----
def stem_docfreq(pagesoups):
    df = defaultdict(set)
    for pi, body in enumerate(pagesoups):
        for el in body.find_all(True):
            for c in (el.get("class") or []):
                s = stem(c.strip())
                if s and not is_util(s):
                    df[s].add(pi)
    return {s: len(ps) for s, ps in df.items()}

# ---- annotate one page (post-order) ----
def annotate(el, stemdf, keep_el=False):
    """Post-order annotate to the fine-signal tree. keep_el=True carries the source bs4
    element as node["_el"] so the content bridge can recover byte-exact outerHTML
    (str(node["_el"])) — zone_detect makes the boundary decision; the markup is recovered here."""
    tag = el.name.lower()
    if tag in DROP:
        return None
    own, kids = [], []
    for c in el.children:
        nm = getattr(c, "name", None)
        if nm is None:
            if isinstance(c, Comment):
                continue
            t = " ".join(str(c).split())
            if t:
                own.append(t)
        else:
            sub = annotate(c, stemdf, keep_el)
            if sub is not None:
                kids.append(sub)
    text = (" ".join(own) + " " + " ".join(k["text"] for k in kids)).strip().lower()
    tlen = len(text)
    alen = tlen if tag == "a" else sum(k["alen"] for k in kids)
    key, tier = identity(tag, el.attrs, stemdf)
    node = {"tag": tag, "key": key, "tier": tier, "text": text, "tlen": tlen, "alen": alen,
            "size": 1 + sum(k["size"] for k in kids), "kids": kids}
    if keep_el:
        node["_el"] = el
    return node

def walk(node):
    """Pre-order traversal of an annotated tree (public helper for callers / the content bridge)."""
    yield node
    for k in node["kids"]:
        yield from walk(k)

def load(proj):
    """(slug, body) per page, read from the SCOPED MIRROR when one exists.

    scope_apply.py makes local-mirror/ the scoped reference every downstream step
    consumes; identification must read the same bytes. Reading the raw crawl cache
    instead let excluded junk BE the model: on salonphoto the OneTrust consent SDK
    (27/27 pages) produced 20+ of 35 ABSOLUTE keys — Ot Grp Hdr1, Ot Sdk Row,
    Ot Pc Scrollbar, Dialog — i.e. the zoning map's chrome tier was mostly a cookie
    banner. Falls back to `cachedAt` when no mirror has been built yet; the mode is
    recorded on `load.source` and stamped into the emitted JSON (gated by
    probes/zone-source.py)."""
    base = f"{REPO}/projects/{proj}"
    inv = json.load(open(f"{base}/workflow-output/page-inventory.json"))
    mirror = f"{base}/workflow-output/local-mirror"
    pages, modes = [], set()
    for pg in inv["pages"]:
        cand = [(os.path.join(mirror, f"{pg.get('slug', '')}.html"), "scoped-mirror"),
                (os.path.join(base, pg.get("cachedAt", "")), "raw-cache")]
        for p, mode in cand:
            if pg.get("slug") and os.path.exists(p) and os.path.isfile(p):
                body = BeautifulSoup(open(p, encoding="utf-8", errors="replace").read(),
                                     "lxml").body
                if body:
                    pages.append((pg["slug"], body))
                    modes.add(mode)
                break
    load.source = modes.pop() if len(modes) == 1 else ("mixed" if modes else "none")
    return pages

def new_agg():
    return {"pages": set(), "inst": 0, "sib": 0, "tier": None, "parents": Counter(),
            "texts": set(), "sizes": [], "ld_sum": 0.0, "ld_n": 0, "sample": ("", "")}

def aggregate(node, pi, agg, parent_key, covered, under):
    key = node["key"]
    nowunder = under
    if key:
        e = agg[key]
        e["pages"].add(pi); e["inst"] += 1; e["tier"] = node["tier"]
        if parent_key:
            e["parents"][parent_key] += 1
        if node["tlen"]:
            e["ld_sum"] += node["alen"] / node["tlen"]; e["ld_n"] += 1
        if len(e["texts"]) < 400:
            e["texts"].add(node["text"][:60])
        e["sizes"].append(node["size"])
        if node["text"] and len(node["text"]) > len(e["sample"][0]):
            e["sample"] = (node["text"][:120], node["tag"])
        parent_key = key
        nowunder = True
    if not under:  # count nodes newly covered by an anchor subtree root
        pass
    ck = Counter(k["key"] for k in node["kids"] if k["key"])
    for k, c in ck.items():
        if c >= 2:
            agg[k]["sib"] = max(agg[k]["sib"], c)
    for k in node["kids"]:
        aggregate(k, pi, agg, parent_key, covered, nowunder)

def coverage(node, under):
    """count nodes that sit inside at least one anchor subtree."""
    now = under or (node["key"] is not None)
    c = 1 if now else 0
    for k in node["kids"]:
        c += coverage(k, now)
    return c

def var(e):
    return len(e["texts"]) / e["inst"] if e["inst"] else 0.0
def ld(e):
    return e["ld_sum"] / e["ld_n"] if e["ld_n"] else 1.0

def humanize(key):
    k = key.split(":", 1)[-1]
    for p in ("cmp-", "cmp_", "field--name-field-", "field--name-", "field-", "paragraph--type-",
              "block-", "lfr-", "osb-", "sxa-"):
        if k.startswith(p):
            k = k[len(p):]; break
    k = re.sub(r"[_\-]+", " ", k).strip()
    return k.title() if k else key

def _h64(t):
    return int.from_bytes(hashlib.blake2b(t.encode(), digest_size=8).digest(), "big")
def simhash(feats):
    v = [0] * 64
    for f in feats:
        h = _h64(f)
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1
    return sum((1 << i) for i in range(64) if v[i] > 0)
def hamming(a, b):
    return bin(a ^ b).count("1")

def cluster_struct(ann, site_chrome):
    """Template clustering by STRUCTURAL ARRANGEMENT (chrome-pruned content simhash) — the right
    signal because a component-based CMS reuses the same palette everywhere; what separates
    templates is arrangement/count, not which component keys are present. Bounded auto-knee."""
    def feats(node):
        out = []
        def w(n):
            if n["key"] in site_chrome:
                return
            cs = ",".join(k["tag"] for k in n["kids"] if k["key"] not in site_chrome)
            out.append(f"{n['tag']}[{cs}]")
            for k in n["kids"]:
                w(k)
        w(node)
        return out
    sig = [simhash(feats(a)) for a in ann]
    n = len(sig)
    if n <= 1:
        return [[i] for i in range(n)]
    dist = [[hamming(sig[i], sig[j]) for j in range(n)] for i in range(n)]
    intree = [False] * n; intree[0] = True
    import heapq
    h = [(dist[0][j], 0, j) for j in range(1, n)]; heapq.heapify(h); edges = []
    while h and len(edges) < n - 1:
        w, a, b = heapq.heappop(h)
        if intree[b]:
            continue
        intree[b] = True; edges.append((w, a, b))
        for j in range(n):
            if not intree[j]:
                heapq.heappush(h, (dist[b][j], b, j))
    ws = sorted(w for w, _, _ in edges)
    if max(ws) <= 3:
        thr = max(ws)
    else:
        cand = [i for i in range(len(ws) - 1) if 2 <= ws[i] <= 8 and ws[i + 1] - ws[i] >= 2]
        if cand:
            thr = ws[max(cand, key=lambda i: (ws[i + 1] - ws[i]) / (ws[i] + 1.0))]
        elif ws[0] == 0:
            thr = 0
        else:
            thr = max(0, ws[0] - 1)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for w, a, b in edges:
        if w <= thr:
            parent[find(a)] = find(b)
    cl = defaultdict(list)
    for i in range(n):
        cl[find(i)].append(i)
    return list(cl.values())

def cluster_pages(pages, ann, exclude):
    """template clusters via Jaccard of CONTENT anchor-key sets (site-chrome excluded, so the
    shared header/footer/nav vocabulary can't swamp the signal) — sharp, stable threshold."""
    keysets = []
    for a in ann:
        s = set()
        def walk(n):
            if n["key"] and n["tier"] in ("L0", "L1", "L2", "L3") and n["key"] not in exclude:
                s.add(n["key"])
            for k in n["kids"]:
                walk(k)
        walk(a)
        keysets.append(s)
    n = len(pages)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i in range(n):
        for j in range(i + 1, n):
            a, b = keysets[i], keysets[j]
            if a and b and len(a & b) / len(a | b) >= 0.55:
                parent[find(i)] = find(j)
    cl = defaultdict(list)
    for i in range(n):
        cl[find(i)].append(i)
    return list(cl.values()), keysets

def analyze(proj):
    pages = load(proj)
    bodies = [b for _, b in pages]
    stemdf = stem_docfreq(bodies)
    ann = [annotate(b, stemdf) for b in bodies]
    npages = len(pages)
    agg = defaultdict(new_agg)
    for pi, a in enumerate(ann):
        aggregate(a, pi, agg, None, None, False)
    for e in agg.values():
        e["medsize"] = statistics.median(e["sizes"]) if e["sizes"] else 0
    # structural gate: an L3 key is a COMPONENT boundary only if it wraps a real block
    # (median subtree >=4 nodes); leaf text-style spans (font-body-1, toolstext) are not.
    def is_anchor(k):
        e = agg[k]
        return e["tier"] in ("L0", "L1", "L2") or (e["tier"] == "L3" and e["medsize"] >= 4)
    # ROOT WRAPPERS: a key whose subtree is ~the whole page (median >=55% of page) is the
    # document/layout root (body, Next.js __className, AEM root/responsivegrid) — NOT a zone.
    page_med = statistics.median([a["size"] for a in ann]) if ann else 1
    def is_root_wrapper(k):
        return agg[k]["medsize"] >= 0.55 * page_med
    # SITE CHROME (verification fix): ubiquitous AND boilerplate-or-navigation, NOT a root wrapper,
    # NOT ubiquitous editorial content. The var<=0.25-or-linkdense guard excludes rich-text bodies
    # that merely appear on every page; the root-wrapper guard excludes <body>/page shells.
    landmark = {"role:banner", "role:contentinfo", "tag:header", "tag:footer"}  # nav handled below
    # an ABSOLUTE zone is a CONTENT-BEARING CONTAINER (medsize>=6, has text), not a ubiquitous
    # leaf primitive (Button) or an empty layout grid (grid_helper) — verification residue fix.
    site_chrome = {k for k, e in agg.items()
                   if len(e["pages"]) >= 0.9 * npages and is_anchor(k) and not is_root_wrapper(k)
                   and e["medsize"] >= 6 and e["sample"][0]
                   and (var(e) <= 0.25 or ld(e) >= 0.55)} | \
                  {k for k in agg if k in landmark}
    # nav: a landmark nav is chrome only if it is the MAIN nav (many links), not the breadcrumb
    for k in ("role:navigation", "tag:nav"):
        if k in agg and ld(agg[k]) >= 0.5 and not is_root_wrapper(k):
            site_chrome.add(k)
    clusters = cluster_struct(ann, site_chrome)
    clusters.sort(key=len, reverse=True)
    page_cl = {}
    for ci, mem in enumerate(clusters):
        for m in mem:
            page_cl[m] = ci
    for k, e in agg.items():
        cls_pages = defaultdict(set)
        for pi in e["pages"]:
            cls_pages[page_cl[pi]].add(pi)
        e["spread"] = len(cls_pages)
        e["bestcov"] = max(((len(ps) / len(clusters[ci]), ci) for ci, ps in cls_pages.items()),
                           default=(0, -1))
    def scope(k, e):
        if is_root_wrapper(k):
            return "ROOT"
        if k in site_chrome or k in landmark:
            return "ABSOLUTE"
        if e["sib"] >= 3:            # >=3 identical siblings is the most specific signal → record
            return "RECORD"
        bc, bci = e["bestcov"]
        if bc >= 0.8 and bci >= 0 and len(clusters[bci]) >= 2 and e["spread"] <= 2:
            return "TEMPLATE"
        return "COMPONENT"
    for k, e in agg.items():
        e["scope"] = scope(k, e)
    # coverage of DOM by anchors
    tot = sum(a["size"] for a in ann)
    cov = sum(coverage(a, False) for a in ann)
    # containment children map (dominant-parent)
    children = defaultdict(list)
    for k, e in agg.items():
        if e["parents"]:
            dp = e["parents"].most_common(1)[0][0]
            children[dp].append(k)
    tiers = Counter(agg[k]["tier"] for k in agg if is_anchor(k))
    return dict(proj=proj, npages=npages, agg=agg, clusters=clusters, children=children,
                cov=cov, tot=tot, tiers=tiers, page_cl=page_cl, var=var, ld=ld,
                is_anchor=is_anchor, site_chrome=site_chrome, is_root_wrapper=is_root_wrapper)

def report(R):
    proj, npages, agg = R["proj"], R["npages"], R["agg"]
    print(f"\n{'='*80}\n{proj}: {npages} pages | {len(agg)} identity keys | "
          f"DOM coverage by anchors={100*R['cov']/R['tot']:.0f}% | tiers={dict(R['tiers'])} | "
          f"{len(R['clusters'])} templates {sorted((len(c) for c in R['clusters']),reverse=True)}\n{'='*80}")
    def line(k, e):
        return (f"    [{e['tier']}] pg={len(e['pages']):2d} inst={e['inst']:3d} sib={e['sib']:2d} "
                f"var={R['var'](e):.2f} ld={R['ld'](e):.2f}  {humanize(k):22.22s} «{e['sample'][0][:52]}»")
    isa = R["is_anchor"]
    for sc in ("ABSOLUTE", "TEMPLATE", "COMPONENT", "RECORD"):
        ks = [k for k in agg if agg[k]["scope"] == sc and isa(k)]
        ks.sort(key=lambda k: (len(agg[k]["pages"]), agg[k]["inst"]), reverse=True)
        print(f"\n### {sc}  [{len(ks)} keys]")
        for k in ks[:10]:
            print(line(k, agg[k]))
            for ck in sorted(R["children"].get(k, []),
                             key=lambda c: agg[c]["inst"], reverse=True)[:4]:
                if isa(ck):
                    print("      ↳ " + line(ck, agg[ck]).strip())

def regime(R):
    n = sum(R["tiers"].values()) or 1
    l0 = R["tiers"].get("L0", 0); l2 = R["tiers"].get("L2", 0); l3 = R["tiers"].get("L3", 0)
    if l0 >= 0.15 * n:
        return "explicit markers (data-component / itemtype)"
    if (R["tiers"].get("L2", 0) + l0) >= 0.4 * n:
        return "framework-semantic classes"
    if l3 >= 0.6 * n:
        return "recurring classes (needs regime guard)"
    return "mixed"

LIBRARY_TYPES = {"button", "chevronLink", "heading", "richText", "image", "tag", "logo",
                 "divider", "iconWithText", "faqItem", "card", "tab", "section", "gridRow",
                 "cardGrid", "logoWall", "carousel", "tabs", "accordion"}

def _type_from_marker(v):
    """A component's explicit marker value → a clean camelCase type name.
    'page_navigation' → 'pageNavigation', 'Hero-Banner' → 'heroBanner'."""
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", v) if p]
    if not parts or not parts[0][0].isalpha():
        return None
    return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def library_map(key, tier, scope, sib, has_children):
    """Map a detected identity key to ONE base-library component type + confidence [0,1].
    Deterministic word-matching on the (framework-stripped) key + structure; confidence<0.5 =
    weak → defer to DeepSeek/human for name+mapping (verbatim rawHtml fallback until then)."""
    k = key.split(":", 1)[-1].lower()
    def has(*ws):
        return any(w in k for w in ws)
    if has("carousel", "slider", "swiper", "slick", "owl-carousel"):
        return ("carousel", 0.9)
    if has("accordion", "collapsible"):
        return ("accordion", 0.85)
    if k.endswith("tabs") or (has("tab") and has_children):
        return ("tabs", 0.8)
    if has("tabpanel", "tab-panel") or (has("tab") and not has_children):
        return ("tab", 0.7)
    if has("logowall", "logo-wall", "logos", "logo-grid", "brands-logo"):
        return ("logoWall", 0.85)
    if has("logo"):
        return ("logo", 0.7)
    if has("faq"):
        return ("faqItem" if scope == "RECORD" or sib >= 3 else "accordion", 0.75)
    # card-INTENT words only. The bare "grid" token was dropped: it matched layout
    # frameworks (aem-Grid, responsivegrid, Bootstrap main-grid, asr-grid-layouts) and
    # typed heroes/section wrappers as cardGrid via this path (measured on contentful:
    # ~66 zero-child "cardGrid" heroes). A genuine grid of cards is reached through the
    # selective-parent path, which is now gated by the is_card_grid positive-evidence test.
    if (has("card-grid", "cardgrid", "cards", "card-list") and has_children):
        return ("cardGrid", 0.7)
    if has("card", "teaser", "tile", "listing-item", "article-card"):
        return ("card", 0.75)
    if has("button", "btn") or k.endswith("cta"):
        return ("button", 0.7)
    if has("heading", "title", "headline") and not has_children:
        return ("heading", 0.6)
    if has("rich-text", "richtext", "body", "paragraph", "copy", "description", "prose", "wysiwyg"):
        return ("richText", 0.65)
    if has("image", "picture", "media", "photo", "feature-image", "hero-image"):
        return ("image", 0.6)
    if has("badge", "pill") or k == "tag":
        return ("tag", 0.5)
    if has("divider", "separator"):
        return ("divider", 0.5)
    if has("icon") and has_children:
        return ("iconWithText", 0.5)
    # no base-library WORD matched — but if the author EXPLICITLY marked this a
    # component (data-component/itemtype → `cmp:X`), TRUST that name as the type
    # with high confidence. The author declared it; deterministic, before any LLM
    # arbitration. (Residue with NO marker still falls to the weak fallbacks below.)
    if key.startswith("cmp:"):
        name = _type_from_marker(k)
        if name:
            return (name, 0.85)
    if scope == "RECORD":
        return ("card", 0.4)
    if has("row", "grid", "col", "column"):
        return ("gridRow", 0.45)
    if has_children or has("section", "block", "band", "module", "zone", "container", "wrapper", "panel"):
        return ("section", 0.4)
    return ("richText", 0.3)

def emit_json(R, path):
    agg, isa, isroot = R["agg"], R["is_anchor"], R["is_root_wrapper"]
    # top-level anchors per scope: parent is body / a ROOT wrapper (transparent) / a different
    # scope. Treating root wrappers as transparent is the verification fix that lets the real
    # footer/nav (children of the page shell) surface at the ABSOLUTE top level.
    def is_toplevel(k):
        p = agg[k]["parents"].most_common(1)
        if not p:
            return True
        pk = p[0][0]
        if not isa(pk) or isroot(pk):
            return True
        return agg[pk]["scope"] != agg[k]["scope"]
    def node(k):
        e = agg[k]
        kids = [c for c in sorted(R["children"].get(k, []), key=lambda c: agg[c]["inst"], reverse=True)
                if isa(c)][:6]
        lib, conf = library_map(k, e["tier"], e["scope"], e["sib"], bool(kids))
        return {"name": humanize(k), "key": k, "tier": e["tier"], "pages": len(e["pages"]),
                "inst": e["inst"], "sib": e["sib"], "var": round(R["var"](e), 2),
                "ld": round(R["ld"](e), 2), "library": lib, "library_conf": conf,
                "sample": e["sample"][0][:110],
                "children": [{"name": humanize(c), "tier": agg[c]["tier"], "pages": len(agg[c]["pages"]),
                              "inst": agg[c]["inst"],
                              "library": library_map(c, agg[c]["tier"], agg[c]["scope"], agg[c]["sib"],
                                                     bool(R["children"].get(c)))[0],
                              "sample": agg[c]["sample"][0][:70]} for c in kids]}
    out = {"proj": R["proj"], "npages": R["npages"], "regime": regime(R),
           "coverage": round(100 * R["cov"] / R["tot"]), "tiers": dict(R["tiers"]),
           "ntemplates": len(R["clusters"]), "templates": [], "scopes": {}}
    slugs = [s for s, _ in load(R["proj"])]
    out["source"] = getattr(load, "source", "unknown")
    out["templates"] = [sorted(slugs[m] for m in mem) for mem in R["clusters"]]
    for sc in ("ABSOLUTE", "TEMPLATE", "COMPONENT", "RECORD"):
        ks = [k for k in agg if agg[k]["scope"] == sc and isa(k) and is_toplevel(k)]
        ks.sort(key=lambda k: (len(agg[k]["pages"]), agg[k]["inst"]), reverse=True)
        out["scopes"][sc] = [node(k) for k in ks[:14]]
    provenance.stamp_json(out, "zone_detect.py", page_set=slugs)
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)

def scaling(proj):
    """cost scales with component VOCABULARY, not page count: #distinct anchor keys vs #pages."""
    pages = load(proj)
    bodies = [b for _, b in pages]
    stemdf = stem_docfreq(bodies)
    ann = [annotate(b, stemdf) for b in bodies]
    seen = set()
    curve = []
    for pi, a in enumerate(ann):
        def w(n):
            if n["key"] and n["tier"] in ("L0", "L1", "L2"):
                seen.add(n["key"])
            for k in n["kids"]:
                w(k)
        w(a)
        curve.append((pi + 1, len(seen)))
    return curve

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--scaling":
        proj = sys.argv[1]
        cur = scaling(proj)
        pts = [cur[0], cur[len(cur)//4], cur[len(cur)//2], cur[3*len(cur)//4], cur[-1]]
        print(f"{proj:16s} vocab-vs-pages: " + " ".join(f"{p}p→{v}" for p, v in pts) +
              f"  | last-quarter growth: {cur[-1][1]-cur[3*len(cur)//4][1]} new keys over "
              f"{cur[-1][0]-cur[3*len(cur)//4][0]} pages")
    else:
        proj = sys.argv[1] if len(sys.argv) > 1 else "discoverasr"
        R = analyze(proj)
        report(R)
        jd = os.environ.get("ZONE3_JSON_DIR")
        if jd:
            emit_json(R, os.path.join(jd, f"zone3-{proj}.json"))
            print(f"\n[emitted {jd}/zone3-{proj}.json | regime: {regime(R)}]")
