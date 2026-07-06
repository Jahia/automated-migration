#!/usr/bin/env python3
"""extract_content.py — DETERMINISTIC, SOURCE-AGNOSTIC content harvest.

The real content (titles, copy, dates, card text, article bodies, links) lives in
the captured DOM. The old pipeline asked the LLM to "create content" via MCP and
it improvised placeholder/empty results. This extracts the REAL content per page
into content-load.json, which the content step then LOADS into the JCR (the LLM
only maps ambiguous cases, it does not invent text).

Named content-LOAD (not content-data) to disambiguate from the analyze-phase
artifact projects/<project>/workflow-output/content-data.json — a different
schema (a per-page analysis list) with different consumers. This file is the
JCR load payload {adapter, pages:{...}} that load_content.py reads.

Agnostic by design — every CMS renders to HTML:
  * SXA adapter (Sitecore): each `.component > .component-content` is an instance;
    each `field-<name>` is a property value. Precise; used by the 3 current sites.
  * generic adapter (Drupal / WordPress / AEM / plain HTML): walk the main content
    region and emit the ordered block sequence (headings / text / images / links).

Image references are resolved to the filenames produced by extract_media.py, so
the content step can wire the imported DAM nodes.

Usage: python3 orchestration/lib/extract_content.py <project> [site_key]
Writes: orchestration/content/<project>.content-load.json
"""
import html.parser, json, os, re, sys, urllib.parse

IMG_EXT = re.compile(r"\.(png|jpe?g|webp|gif|svg|avif)(\?|$)", re.I)
LAYOUT = re.compile(r"^(component|component-content|container|container-fluid|row|"
                    r"col|col-\w+|mb-\d+|mt-\d+|p-\d+|px-\d+|py-\d+|g-\d+|gap-\d+|"
                    r"d-\w+|text-\w+|fw-\w+|fs-\w+|w-\d+|h-\d+|align-\w+|justify-\w+)$")


def captured_pages(proj):
    # v2 source of truth first: page-inventory.json (crawl output) — its slugs are
    # what semantic_extract, the template clusters and the page-creation step key
    # on ("home", not "index"). Path-derived slugs below are the v1 fallback.
    inv = f"{proj}/workflow-output/page-inventory.json"
    if os.path.isfile(inv):
        try:
            pages = json.load(open(inv)).get("pages", [])
        except Exception:
            pages = []
        out = []
        for p in pages:
            if not p.get("slug"):
                continue
            # prefer the CERTIFIED LOCAL MIRROR page (localized asset refs —
            # passthrough markup must carry the same bytes the ground-truth
            # reference renders); crawl cache is the fallback
            mirror = f"{proj}/workflow-output/local-mirror/{p['slug']}.html"
            cached = os.path.join(proj, p.get("cachedAt") or "")
            path = mirror if os.path.isfile(mirror) else cached
            if os.path.isfile(path):
                out.append((p["slug"], path, None))
        if out:
            return out
    out = []
    capdir = f"{proj}/.reference/captured"
    if os.path.isdir(capdir):
        for fn in sorted(os.listdir(capdir)):
            if fn.endswith(".html"):
                out.append((fn[:-5], os.path.join(capdir, fn), None))
        if out:
            return out
    crawl = f"{proj}/.reference/cache/_crawl"
    for dp, _, fs in os.walk(crawl):
        for fn in fs:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, crawl).split(os.sep)
            base = f"https://{rel[0]}"
            sub = "/".join(rel[1:])[:-5]
            slug = "home" if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", sub) else sub.split("/")[-1]
            out.append((slug, p, base))
    return out


# source-URL -> localized mirror filename (basename under local-mirror/assets/,
# which is where load_content.upload_dam and probes/contribution.py look). Built
# by load_media_map() from the mirror's own already-localized <img>/<source>
# refs plus any URL map the localizer emits (mirror.json / runtime-manifest.json).
# ALL URL forms are registered (rule 31) so a media src in any form resolves.
MEDIA_URL_MAP = {}


def _register_url_forms(mapping, url, fname):
    """Register a source URL in every form markup may reference it (absolute
    https/http, protocol-relative //host, path-only /p) -> the mirror filename."""
    if not url or not fname:
        return
    mapping.setdefault(url, fname)
    if url.startswith(("http://", "https://")):
        proto_rel = re.sub(r"^https?:", "", url)
        mapping.setdefault(proto_rel, fname)
        mapping.setdefault(("http:" if url.startswith("https:") else "https:") + proto_rel, fname)
        path = re.sub(r"^https?://[^/]+", "", url)
        if path and path != url:
            mapping.setdefault(path, fname)


def load_media_map(project):
    """Populate MEDIA_URL_MAP: source-URL (any form) -> mirror asset FILENAME.
    Keyed off whatever the localizer wrote, so media refs the crawl left as
    absolute/space/rendition URLs still resolve to the hashed file on disk.
    Only files that actually exist under local-mirror/assets/ are registered
    (the loader/probe look there) — a runtime-assets-only mapping is skipped so
    filename_for never returns a name the loader can't find."""
    MEDIA_URL_MAP.clear()
    mdir = f"projects/{project}/workflow-output/local-mirror"
    assets_dir = f"{mdir}/assets"
    have = set(os.listdir(assets_dir)) if os.path.isdir(assets_dir) else set()

    def _reg_if_local(url, f):
        # f may be "assets/<hash>.ext" or a bare "<hash>.ext"; only accept when
        # the basename exists under assets/
        base = os.path.basename(f or "")
        if base in have:
            _register_url_forms(MEDIA_URL_MAP, url, base)

    # 1) mirror.json — a per-URL asset map if the localizer emits one (forward-
    # compatible: today it carries counts; the localizer fix may add url->file).
    try:
        mj = json.load(open(f"{mdir}/mirror.json"))
        amap = mj.get("assets")
        if isinstance(amap, dict):
            for k, v in amap.items():
                f = v.get("file") if isinstance(v, dict) else (v if isinstance(v, str) else None)
                if f:
                    _reg_if_local(k, f)
        for entry in (mj.get("urlMap") or mj.get("localizedMap") or {}).items() \
                if isinstance(mj.get("urlMap") or mj.get("localizedMap"), dict) else []:
            _reg_if_local(entry[0], entry[1])
    except Exception:
        pass
    # 2) runtime-manifest.json — same shape as RUNTIME_URL_MAP; register only the
    # entries whose file the localizer copied under assets/ (not runtime-assets/).
    try:
        rm = json.load(open(f"{mdir}/runtime-manifest.json"))
        for k, v in (rm.get("assets") or {}).items():
            f = (v or {}).get("file")
            if f:
                _reg_if_local(k, f)
    except Exception:
        pass


def filename_for(url):
    if not url:
        return "image.img"
    # consult the mirror's URL->localized-file mapping FIRST (rule 31) so a media
    # ref the crawl left as an absolute/space/rendition URL still resolves to the
    # hashed asset file the localizer wrote under assets/.
    if url in MEDIA_URL_MAP:
        return MEDIA_URL_MAP[url]
    name = os.path.basename(urllib.parse.urlparse(url).path) or "image"
    name = urllib.parse.unquote(name)
    return re.sub(r"[^A-Za-z0-9._-]", "-", name if IMG_EXT.search(name) else name + ".img")


def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()


class SXAContent(html.parser.HTMLParser):
    """Per-page SXA instances: each .component -> {type, fields:{name:text}, images, links}."""
    # repeated item wrappers that are NOT .component-wrapped (cards in a picture-grid,
    # partner logos, popin items). Each such element inside a component is a CHILD
    # item — without this the items collapse into the parent and the grid renders empty.
    ITEM_MARKERS = {"card", "vignette", "mosaic-item", "partner-item", "popin-item",
                    "tab-pane", "accordion-item", "speaker", "conference-item"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.instances = []
        self.compstack = []          # (instance_idx, divdepth)
        self.itemstack = []          # (instance_idx, divdepth) — repeated items within a component
        self.divdepth = 0
        self.fieldstack = []         # (instance_idx, fieldname, divdepth)
        self.in_a = None             # (instance_idx, href, text_parts)

    def _cur(self):
        """The instance fields/images/links attach to: deepest item, else component."""
        if self.itemstack:
            return self.itemstack[-1][0]
        return self.compstack[-1][0] if self.compstack else None

    def _start_component(self, toks):
        after = [t for t in toks if not LAYOUT.match(t)]
        ctype = after[0] if after else "unknown"
        parent = self._cur()
        self.instances.append({"type": ctype, "parent": parent,
                               "fields": {}, "images": [], "links": []})
        self.compstack.append((len(self.instances) - 1, self.divdepth))

    def _start_item(self, marker):
        # an item is a child of its enclosing component
        parent = self.compstack[-1][0] if self.compstack else None
        self.instances.append({"type": marker, "parent": parent, "item": True,
                               "fields": {}, "images": [], "links": []})
        self.itemstack.append((len(self.instances) - 1, self.divdepth))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        toks = (a.get("class") or "").split()
        if tag == "div":
            self.divdepth += 1
            if "component" in toks and "component-content" not in toks:
                self._start_component(toks)
            elif self.compstack and (set(toks) & self.ITEM_MARKERS):
                self._start_item(next(t for t in toks if t in self.ITEM_MARKERS))
        cur = self._cur()
        if cur is None:
            return
        # field-<name> element -> capture its text into fields[name]
        for t in toks:
            if t.startswith("field-"):
                self.fieldstack.append((cur, t[len("field-"):], self.divdepth))
        # images inside this component/item
        if tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src and IMG_EXT.search(src) and not src.startswith("data:"):
                self.instances[cur]["images"].append(
                    {"file": filename_for(src), "alt": clean(a.get("alt", ""))})
        # links inside this component/item
        if tag == "a" and a.get("href"):
            self.in_a = (cur, a["href"], [])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("img",):
            self.in_a = self.in_a  # img self-closing handled above

    def handle_data(self, data):
        d = data.strip()
        if not d:
            return
        if self.in_a is not None:
            self.in_a[2].append(data)
        if self.fieldstack:
            ci, name, _ = self.fieldstack[-1]
            self.instances[ci]["fields"][name] = clean(
                (self.instances[ci]["fields"].get(name, "") + " " + data))

    def handle_endtag(self, tag):
        if tag == "a" and self.in_a is not None:
            ci, href, parts = self.in_a
            txt = clean("".join(parts))
            if txt or href:
                self.instances[ci]["links"].append({"text": txt, "href": href})
            self.in_a = None
        if tag == "div":
            if self.fieldstack and self.fieldstack[-1][2] == self.divdepth:
                self.fieldstack.pop()
            if self.itemstack and self.itemstack[-1][1] == self.divdepth:
                self.itemstack.pop()
            if self.compstack and self.compstack[-1][1] == self.divdepth:
                self.compstack.pop()
            self.divdepth -= 1


class GenericContent(html.parser.HTMLParser):
    """Fallback for non-SXA CMSes: ordered content blocks in the main region."""
    SKIP = {"script", "style", "nav", "footer", "header"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.skip = 0
        self.cur = None      # (kind, parts)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.cur = ("heading", [])
        elif tag in ("p", "li", "blockquote"):
            self.cur = ("text", [])
        elif tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src and IMG_EXT.search(src) and not src.startswith("data:"):
                self.blocks.append({"type": "image", "file": filename_for(src),
                                    "alt": clean(a.get("alt", ""))})
        elif tag == "a" and a.get("href"):
            self.cur = ("link", [a["href"]])

    def handle_data(self, data):
        if self.skip or self.cur is None:
            return
        self.cur[1].append(data)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.cur and tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "a"):
            kind, parts = self.cur
            if kind == "link":
                href = parts[0]
                txt = clean("".join(parts[1:]))
                if txt:
                    self.blocks.append({"type": "link", "text": txt, "href": href})
            else:
                txt = clean("".join(parts))
                if len(txt) >= 2:
                    self.blocks.append({"type": kind, "text": txt})
            self.cur = None


def detect_sxa(htmltext):
    return 'class="component' in htmltext and "field-" in htmltext


_ASSET_REF_RE = re.compile(r'(?<![\w/-])(\.?/?)((?:runtime-)?assets/)')

# ── giant inline data-URIs -> materialized static assets (2026-07-06) ──
# A skeleton holding a multi-MB base64 image blows the loader's 200_000-char
# JCR write cap: the property is silently TRUNCATED and the image + all
# trailing markup vanish from the render (observed: chelseafc 1.1MB + 2.6MB
# skeletons -> two missing card images, whole-page pixel cascade). Decode any
# data-URI >= 64KB to a sha1-named file in the mirror assets dir (the same dir
# import_assets copies to module static) and reference it like any other asset.
_DATA_URI_DIR = None   # set by main(): <proj>/workflow-output/local-mirror/assets
_DATA_URI_RE = re.compile(
    r'(src=["\'])(data:image/(png|jpe?g|gif|webp|svg\+xml);base64,([A-Za-z0-9+/=]{65536,}))(["\'])')
_DATA_URI_EXT = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "gif": "gif",
                 "webp": "webp", "svg+xml": "svg"}


def _materialize_data_uris(html, base):
    if not _DATA_URI_DIR or "data:image" not in html:
        return html
    import base64 as _b64
    import hashlib as _hl

    def sub(m):
        try:
            data = _b64.b64decode(m.group(4))
        except Exception:
            return m.group(0)
        name = _hl.sha1(data).hexdigest()[:16] + "." + _DATA_URI_EXT[m.group(3)]
        dest = os.path.join(_DATA_URI_DIR, name)
        if not os.path.isfile(dest):
            with open(dest, "wb") as f:
                f.write(data)
        return m.group(1) + base + "assets/" + name + m.group(5)

    return _DATA_URI_RE.sub(sub, html)

# runtime-manifest URL map (P3): source URLs the mirror serves from its local
# runtime-assets copies (Sitecore /-/media/..., JS-composed CDN paths). The
# LIVE page has no offline resolver — every mapped URL must point at the
# module's static copy or it 404s (observed live: supercar section imagery).
RUNTIME_URL_MAP = {}


def load_runtime_map(project):
    RUNTIME_URL_MAP.clear()
    try:
        rm = json.load(open(f"projects/{project}/workflow-output/local-mirror/runtime-manifest.json"))
    except Exception:
        return
    for k, v in (rm.get("assets") or {}).items():
        f = (v or {}).get("file")
        if not f:
            continue
        RUNTIME_URL_MAP[k] = f
        # markup references the SAME asset in several URL forms — register each
        # so the static rewrite matches whatever the captured HTML actually uses
        # (observed live: manifest key `https://host/path`, HTML uses the
        # protocol-relative `//host/path`; contentful CDN logos + discoverasr's
        # absolute refs were left un-rewritten -> broken for real visitors).
        if k.startswith(("http://", "https://")):
            proto_rel = re.sub(r"^https?:", "", k)           # //host/path
            RUNTIME_URL_MAP.setdefault(proto_rel, f)
            RUNTIME_URL_MAP.setdefault(
                ("http:" if k.startswith("https:") else "https:") + proto_rel, f)
            path = re.sub(r"^https?://[^/]+", "", k)          # /path
            if path and path != k:
                RUNTIME_URL_MAP.setdefault(path, f)


def rewrite_asset_refs(html, base):
    """Mirror markup references assets RELATIVELY (`assets/<hash>`) — valid at
    the mirror root, broken under /sites/... Rewrite to the module's static
    mirror copy (assetBase, e.g. /modules/<m>/static/). Runtime-manifest URLs
    (absolute source paths) are rewritten too, raw and attr-escaped forms."""
    if not base or not html:
        return html
    html = _materialize_data_uris(html, base)
    html = _ASSET_REF_RE.sub(lambda m: base + m.group(2), html)
    for k in sorted(RUNTIME_URL_MAP, key=len, reverse=True):
        if k in html or k.replace("&", "&amp;") in html:
            tgt = base + RUNTIME_URL_MAP[k]
            html = html.replace(k, tgt).replace(k.replace("&", "&amp;"), tgt)
    return html


def _library_atom(plan, parent_idx, facts, name, base):
    """Build one COMPOSABLE library atom instance (P6.3 logoWall, P6.3-bis
    carousel slide / tabs pane) as a child of `parent_idx`.

    FIDELITY-FIRST (rule 26 verbatim-default): the atom carries its VERBATIM
    cleaned source markup in `imgOrig` (module-static refs). The loader/view
    renders it as-is while the atom's picked image weakref still targets the DAM
    copy of the original — byte-exact by construction. The first image + first
    link (facts.src / facts.href) surface as the editable weakref + j:linkType
    slots; the rest of the markup is the verbatim default. Generic across atom
    kinds: a logo carries a media-only `orig`, a slide/tab carries a rich block
    `orig` + optional title/active — the same contract, no bespoke logic."""
    return {
        "type": plan["kind"] + "-atom", "nodeType": plan["atomType"],
        "parent": parent_idx, "libraryAtom": True,
        "slot": name,
        "variant": facts.get("variant", "brand"),
        "breakClass": facts.get("breakClass", ""),
        "anchorClass": facts.get("anchorClass", ""),
        "elClass": facts.get("elClass", ""),
        # slide/tab label (tabs) or logo title; drives the atom's editable title
        "atomTitle": facts.get("title", ""),
        "active": bool(facts.get("active", False)),
        "imgTitle": facts.get("title", ""),
        # verbatim source markup on module-static refs (rule 26 verbatim default)
        "imgOrig": rewrite_asset_refs(facts.get("orig", ""), base),
        "imageAltText": facts.get("alt", ""),
        "imageFile": filename_for(facts.get("src", "")),
        "href": facts.get("href", ""),
        "fields": {}, "images": [], "links": [],
    }


def load_overrides(project):
    """workflow-output/passthrough-overrides.json — the fidelity/semantic DIAL:
    {"demoteRoles": ["*"|role...], "promoteRoles": [role...],
     "chromePassthrough": bool, "assetBase": "/modules/<m>/static/"}.
    Demoted component regions load as verbatim rawHtml; promoteRoles WINS over
    demoteRoles/"*" — promoted regions load as semantic instances carrying a
    SKELETON (their own markup with field values replaced by {{f:name}}
    markers) so the skeleton view renders pixel-identical with editable fields
    (QUALITY-PLAN P2)."""
    p = f"projects/{project}/workflow-output/passthrough-overrides.json"
    try:
        return json.load(open(p))
    except Exception:
        return {}


def _reparse_root(html):
    """Fragment -> single root Tag, ONLY when bs4 re-serialization is byte-
    idempotent (str(parse(html)) == html). Otherwise None — the caller keeps
    the fragment as verbatim rawHtml rather than risk serialization drift."""
    from bs4 import BeautifulSoup, Tag
    if not (html or "").strip().startswith("<"):
        return None
    frag = BeautifulSoup(html, "lxml")
    body = frag.body or frag
    roots = [c for c in body.children if isinstance(c, Tag)]
    if len(roots) != 1:
        return None
    if str(roots[0]) != html:
        return None
    return roots[0]


_EXT_SCRIPT_RE = re.compile(
    r'<script\b[^>]*\bsrc=["\'](?:https?:)?//[^"\']*["\'][^>]*>\s*</script>', re.I)


def _attrs_of(el):
    return {k: (" ".join(v) if isinstance(v, list) else str(v))
            for k, v in (el.attrs or {}).items()}


def page_shell(txt, base):
    """Per-page SHELL spec (the fidelity decider on JS-dependent sites): body
    attributes (Drupal keys CSS off body classes), the exact ancestor chain
    from <body> down to <main> (rebuilt as real elements by the template — no
    flattening, descendant CSS keeps working), and the BALANCED sibling markup
    before/after each chain level — sprites, drupalSettings JSON, local
    scripts, header/footer chrome, all verbatim. External-host script tags are
    stripped (the offline reference blocks them; parity means the live page
    must not fire them either).

    Also captures the ORDERED per-page <head> resources (stylesheets, scripts,
    inline scripts incl. drupalSettings JSON, inline styles) — Drupal aggregates
    CSS/JS per page and keys behaviors off inline settings; a cross-page union
    is not faithful. External-host resources are skipped (parity with the
    offline reference).

    Returns {bodyAttrs, mainAttrs, levels:[{tag, attrs, before, after}...],
    head:[{kind, ...}]} where levels[0] is body itself."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(txt, "lxml")
    body = soup.body
    if body is None:
        return None
    main = body.find("main") or body.find(attrs={"role": "main"})
    if main is None:
        # embed/landing page without <main>: the BODY is the content root —
        # head + body attrs still matter (the shell renders a <main> wrapper
        # around the area; pixel-neutral, judged by the ground-truth gate)
        main = body

    head_items = []
    for el in (soup.head.children if soup.head else []):
        if getattr(el, "name", None) is None:
            continue
        if el.name == "link" and "stylesheet" in (el.get("rel") or []):
            href = el.get("href") or ""
            if href.startswith(("http:", "https:", "//")):
                continue
            head_items.append({"kind": "css",
                               "href": rewrite_asset_refs(href, base)})
        elif el.name == "script":
            src = el.get("src") or ""
            if src:
                if src.startswith(("http:", "https:", "//")):
                    continue
                head_items.append({"kind": "script",
                                   "src": rewrite_asset_refs(src, base),
                                   "defer": el.has_attr("defer"),
                                   "async": el.has_attr("async")})
            else:
                head_items.append({"kind": "inline-script",
                                   "type": el.get("type") or "",
                                   "attrs": _attrs_of(el),
                                   "text": rewrite_asset_refs(el.string or el.get_text(), base)})
        elif el.name == "style":
            head_items.append({"kind": "style",
                               "text": rewrite_asset_refs(el.get_text(), base)})

    chain = [body]
    if main is not body:
        p = main.parent
        anc = []
        while p is not None and p is not body:
            anc.append(p)
            p = p.parent
        chain += list(reversed(anc))  # body, wrapper1, ..., main.parent

    from bs4 import Comment

    def ser(node):
        # bs4 str(Comment) yields the BARE text — the <!-- --> markers must be
        # re-wrapped or comment content becomes VISIBLE text (observed live:
        # 'End Google Tag Manager' + '#wrapper' markers rendered on supercar)
        if isinstance(node, Comment):
            return f"<!--{node}-->"
        return str(node)

    def chunk(parts):
        html = _EXT_SCRIPT_RE.sub("", rewrite_asset_refs("".join(parts), base))
        return html.strip()

    levels = []
    for i, node in enumerate(chain):
        nxt = chain[i + 1] if i + 1 < len(chain) else main
        before, after, seen = [], [], False
        if node is not main:  # main==body (no-main page): its children all
            for child in node.children:  # flow through the partition instances
                if child is nxt:
                    seen = True
                    continue
                (after if seen else before).append(ser(child))
        levels.append({
            "tag": node.name if node is not body else "body",
            "attrs": _attrs_of(node),
            "before": chunk(before),
            "after": chunk(after),
        })
    # inner wrapper chain (main -> content root, e.g. Drupal's region--content):
    # recomposed INSIDE <main> around the Area — partition/top-groups operate at
    # the content-root altitude (see semantic_extract.main_content_root)
    from semantic_extract import main_content_root
    _croot, inner_chain = main_content_root(main)
    inner_levels = []
    for i, node in enumerate(inner_chain):
        parent = main if i == 0 else inner_chain[i - 1]
        before, after, seen = [], [], False
        for child in parent.children:
            if child is node:
                seen = True
                continue
            (after if seen else before).append(ser(child))
        inner_levels.append({"tag": node.name, "attrs": _attrs_of(node),
                             "before": chunk(before), "after": chunk(after)})

    return {
        "bodyAttrs": _attrs_of(body),
        "mainAttrs": _attrs_of(main),
        "levels": levels,
        "innerLevels": inner_levels,
        "head": head_items,
    }


def semantic_page(txt, slug, overrides=None, manifest=None):
    """v2 adapter: reuse semantic_extract's deterministic component walk so each
    instance's `type` is the same ROLE the manifest's instanceTypeMap keys on —
    the whole point of the bridge (load_content resolves role -> ns:nodeType).

    Emits load-shaped instances with parents always preceding their children.
    Main-region instances follow the P1.2 partition in DOCUMENT ORDER, with
    uncovered regions emitted as `rawHtml` passthrough instances — every content
    leaf of <main> reaches the JCR exactly once (the ≥99 % fidelity invariant).

    Overrides (P1 dial): demoted roles load as verbatim rawHtml; chrome
    (header/nav/footer) can load as area-flagged rawHtml singletons.

    P2.5: promoted groups are DECOMPOSED (semantic_extract.decompose_group) —
    repeated items become child payloads (own skeleton + title/body* fields),
    group text runs become richtext body* props. Byte-identity is self-checked;
    any failure falls back to verbatim rawHtml (fidelity before contribution)."""
    import semantic_extract as SE
    from semantic_extract import extract_page  # bs4/lxml — pipeline dependency
    ov = overrides or {}
    demote = set(ov.get("demoteRoles") or [])
    demote_all = "*" in demote
    promote = set(ov.get("promoteRoles") or [])
    chrome_pass = bool(ov.get("chromePassthrough"))
    base = ov.get("assetBase") or ""
    # manifest awareness: items become CHILD NODES only when the mapped type
    # declares a childType (else the loader could not create them and the
    # unresolved {{child:N}} markers would break fidelity)
    itm = {k.lower(): v for k, v in ((manifest or {}).get("instanceTypeMap") or {}).items()}
    container_types = {c["nodeType"] for c in (manifest or {}).get("components", [])
                       if c.get("isContainer") and c.get("childType")}

    def type_allows_items(role):
        return itm.get((role or "").lower()) in container_types

    _, comps, partition = extract_page(txt, slug)
    out, remap = [], {}
    lift_stats = {"byteFail": 0, "emptyShell": 0}

    def emit(i):
        if i in remap:
            return remap[i]
        c = comps[i]
        pi = c.get("parentIndex")
        parent = emit(pi) if pi is not None else None
        fields = {}
        headings = c.get("headings") or []
        for n, h in enumerate(headings):
            fields["title" if n == 0 else f"title-{n + 1}"] = h
        body = c.get("fullText") or ""
        for h in headings:  # heading text repeats inside text_parts — strip once
            body = body.replace(h, " ", 1)
        body = clean(body)
        if len(body) >= 2:
            fields["text"] = body[:5000]
        remap[i] = len(out)
        out.append({
            "type": c["role"],
            "parent": parent,
            "fields": fields,
            "images": [{"file": filename_for(d["src"]), "alt": d.get("alt", "")}
                       for d in (c.get("imageDetails") or [])],
            "links": [{"text": d.get("text", ""), "href": d["href"]}
                      for d in (c.get("linkDetails") or [])],
        })
        return remap[i]

    children_of = {}
    for i, c in enumerate(comps):
        pi = c.get("parentIndex")
        if pi is not None:
            children_of.setdefault(pi, []).append(i)

    def subtree(i):
        yield i
        for j in children_of.get(i, []):
            yield from subtree(j)

    regions = partition.get("regions", [])
    main_idx = set()
    for r in regions:
        if r["kind"] == "component" and r.get("compIndex") is not None:
            main_idx.update(subtree(r["compIndex"]))

    def raw_instance(html, leaves=None, area=None):
        inst = {"type": "rawHtml", "parent": None, "passthrough": True,
                "fields": {"html": rewrite_asset_refs(html, base)},
                "images": [], "links": []}
        if area:
            inst["area"] = area
        return inst

    def conv_media(med):
        """Payload media -> load contract: orig markup on module-static refs,
        `file` = the mirror asset the loader uploads to the DAM."""
        return [{"name": m["name"],
                 "orig": rewrite_asset_refs(m["orig"], base),
                 "file": filename_for(m["src"]),
                 "alt": m.get("alt", "")} for m in (med or [])]

    def payload_extras(d):
        return {"media": conv_media(d.get("media")),
                "mediaTotal": d.get("mediaTotal", 0),
                "link": d.get("link"), "linkTotal": d.get("linkTotal", 0)}

    def raw_lifted_instance(el, html):
        """Demoted top group -> ANONYMOUS editable block (P2.5): still an
        honest ns:rawHtml (no invented type name), but its text runs are lifted
        into richtext body* props via the same skeleton mechanism. Headings are
        NOT lifted (rawHtml carries no mix:title) — they join the body runs.
        Returns None when nothing was liftable (plain verbatim raw instead)."""
        if el is None:
            return None
        d = SE.decompose_group(el, allow_items=False, lift_titles=False)
        if not d["ok"]:
            lift_stats["byteFail"] += 1
            return None
        def _has(pl):
            return pl.get("fields") or pl.get("media") or pl.get("link")
        if not _has(d) and not any(_has(ch) for ch in d["children"]):
            return None
        # decompose can emit {{child:N}} markers even with allow_items=False
        # (structural non-item children). Dropping d["children"] left those
        # markers phantom — recompose rendered holes. Carry the child payloads.
        return {"type": "rawHtml", "parent": None, "passthrough": True,
                "fields": {k: rewrite_asset_refs(v, base)
                           for k, v in d["fields"].items()},
                "skeleton": rewrite_asset_refs(d["skeleton"], base),
                "children": [{"fields": {k: rewrite_asset_refs(v, base)
                                         for k, v in ch["fields"].items()},
                              "skeleton": rewrite_asset_refs(ch["skeleton"], base),
                              **payload_extras(ch)} for ch in d["children"]],
                "skeletonSubs": sorted(d["fields"]) + sorted(
                    k for ch in d["children"] for k in ch["fields"]),
                "skeletonMissed": [],
                **payload_extras(d),
                "images": [], "links": []}

    def emit_promoted(ci, group_el=None, group_html=None):
        """Promoted TOP GROUP -> decomposed skeleton instance (P2.5): repeated
        items -> child payloads ({{child:i}} markers), text runs -> richtext
        body* props, headings -> title. All markers placed at DOM level, so
        every loaded field is WIRED to the render by construction. Returns True
        if promoted; False when the group fell back to verbatim rawHtml (byte
        self-check failure or nothing liftable — an empty shell would lie to
        editors)."""
        c = comps[ci]
        el = group_el
        if el is None:
            el = _reparse_root(group_html if group_html is not None
                               else (c.get("outerHTML") or ""))
        if el is None:
            out.append(raw_instance(group_html or c.get("outerHTML") or ""))
            lift_stats["byteFail"] += 1
            for j in subtree(ci):
                remap[j] = None
            return False
        d = SE.decompose_group(el, allow_items=type_allows_items(c["role"]))
        if not d["ok"]:
            out.append(raw_instance(d["original"]))
            lift_stats["byteFail"] += 1
            for j in subtree(ci):
                remap[j] = None
            return False
        def _has_content(pl):
            return pl.get("fields") or pl.get("media") or pl.get("link")
        if not _has_content(d) and not any(_has_content(ch) for ch in d["children"]):
            out.append(raw_instance(d["original"]))  # honest: raw, not a lying type
            lift_stats["emptyShell"] += 1
            for j in subtree(ci):
                remap[j] = None
            return False
        # asset refs -> module static (skeletons AND richtext bodies carry markup)
        def rw_fields(flds):
            return {k: (rewrite_asset_refs(v, base) if k.startswith("body") else v)
                    for k, v in flds.items()}
        out.append({
            "type": c["role"], "parent": None, "promoted": True,
            "fields": rw_fields(d["fields"]),
            "skeleton": rewrite_asset_refs(d["skeleton"], base),
            **payload_extras(d),
            "children": [{"fields": rw_fields(ch["fields"]),
                          "skeleton": rewrite_asset_refs(ch["skeleton"], base),
                          **payload_extras(ch)}
                         for ch in d["children"]],
            "skeletonSubs": sorted(d["fields"]) + sorted(
                k for ch in d["children"] for k in ch["fields"]),
            "skeletonMissed": [],
            "images": [{"file": filename_for(dd["src"]), "alt": dd.get("alt", "")}
                       for dd in (c.get("imageDetails") or [])],
            "links": [{"text": dd.get("text", ""), "href": dd["href"]}
                      for dd in (c.get("linkDetails") or [])],
        })
        for j in subtree(ci):
            remap[j] = None  # absorbed into the skeleton
        return True

    # chrome (header/footer/nav — routed to absolute areas by the loader) and any
    # off-main components first; then <main> strictly in document order.
    # Pages WITHOUT <main> (embed/landing, e.g. Typeform): every top child of
    # <body> already flows through the partition below — emitting "off-main"
    # components here would double-emit fragments (observed: title/svg debris).
    no_main = partition.get("noMain")
    for i in range(len(comps)):
        if no_main:
            break
        if i in main_idx:
            continue
        c = comps[i]
        if chrome_pass and c["position"] in ("header", "footer", "nav") and c["parentIndex"] is None:
            # whole chrome region as an area-flagged verbatim singleton (the
            # loader installs it once under /home/<area>, not per page)
            out.append(raw_instance(c.get("outerHTML") or "", area=c["position"]))
            for j in subtree(i):
                remap[j] = None  # absorbed into the region markup — do not re-emit
            continue
        if remap.get(i, -1) is None:
            continue
        emit(i)

    # Demotion granularity = DIRECT CHILD OF <main> (topIndex group): loading a
    # component region's outerHTML individually drops the wrapper element
    # between <main> and the component (its grid/flex classes) and the layout
    # collapses. A top group whose regions are all passthrough/demoted loads as
    # ONE verbatim blob — wrappers intact. Only a group holding a PROMOTED
    # semantic component falls back to per-region emission (the promoted view
    # then owns its wrapper markup).
    top_levels = partition.get("topLevels", [])
    by_top = {}
    for r in regions:
        by_top.setdefault(r.get("topIndex", -1), []).append(r)

    def region_promoted(r):
        if r["kind"] != "component":
            return False
        ci = r.get("compIndex")
        role = comps[ci]["role"] if ci is not None else None
        if role in promote:      # explicit promotion wins over demote/"*" (P2)
            return True
        return not (demote_all or role in demote)

    demoted_leaves = 0
    promoted_group_leaves = 0
    for ti in sorted(by_top.keys()):
        group = by_top[ti]
        promoted = [r for r in group if region_promoted(r)]
        in_top = 0 <= ti < len(top_levels)
        if promoted and in_top:
            # promotion at TOP-GROUP granularity (same as demotion): the whole
            # top-level child (wrappers intact) becomes one skeleton instance,
            # typed and titled by its dominant promoted region
            dom = max(promoted, key=lambda r: r.get("leaves", 0))
            ok = emit_promoted(dom["compIndex"],
                               group_el=top_levels[ti].get("el"),
                               group_html=top_levels[ti]["html"])
            glv = sum(r.get("leaves", 0) for r in group)
            if ok:
                promoted_group_leaves += glv
            else:
                demoted_leaves += glv
            for r in group:
                if r.get("compIndex") is not None:
                    for j in subtree(r["compIndex"]):
                        remap[j] = None
            continue
        if not promoted and in_top:
            lifted = raw_lifted_instance(top_levels[ti].get("el"),
                                         top_levels[ti]["html"])
            out.append(lifted or raw_instance(top_levels[ti]["html"]))
            demoted_leaves += sum(r.get("leaves", 0) for r in group
                                  if r["kind"] == "component")
            for r in group:
                if r.get("compIndex") is not None:
                    for j in subtree(r["compIndex"]):
                        remap[j] = None
            continue
        for r in group:  # fallback: regions without a top anchor
            if r["kind"] == "component":
                ci = r.get("compIndex")
                if ci is None:
                    continue
                if region_promoted(r):
                    if emit_promoted(ci):
                        promoted_group_leaves += r.get("leaves", 0)
                    else:
                        demoted_leaves += r.get("leaves", 0)
                else:
                    out.append(raw_instance(comps[ci].get("outerHTML") or ""))
                    demoted_leaves += r.get("leaves", 0)
                    for j in subtree(ci):
                        remap[j] = None
            else:
                out.append(raw_instance(r["html"]))

    out = [i for i in out if i is not None]
    parents = {i["parent"] for i in out if i.get("parent") is not None}
    for idx, i in enumerate(out):
        i["empty"] = not (i["fields"] or i["images"] or i["links"]) and idx not in parents

    shell = page_shell(txt, base) if ov.get("shell", True) else None

    # LOADED partition (what actually reaches the JCR) — the analyzer's
    # capability numbers stay in semantic-templates.json pagePartitions
    summary = {k: v for k, v in partition.items() if k not in ("regions", "topLevels")}
    total = summary.get("leavesTotal") or 0
    summary["semanticLeafShare"] = round(promoted_group_leaves / total, 3) if total else None
    summary["demotedLeaves"] = demoted_leaves
    # P2.5 contribution accounting (probes/contribution.py judges the floors)
    summary["liftByteFail"] = lift_stats["byteFail"]
    summary["liftEmptyShell"] = lift_stats["emptyShell"]
    summary["childItems"] = sum(len(i.get("children") or []) for i in out)
    n_comp = sum(1 for i in out if not i.get("passthrough") and i.get("parent") is None
                 and not i.get("area"))
    summary["componentRegions"] = n_comp
    summary["passthroughRegions"] = sum(1 for i in out if i.get("passthrough") and not i.get("area"))
    page = {"adapter": "semantic", "instances": out, "partition": summary}
    if shell:
        page["shell"] = shell
    return page


def vision_page(project, txt, slug, sig_index, overrides=None, manifest=None):
    """VISION adapter (P4): the vision component model DRIVES extraction.

    Instead of re-deriving component boundaries (semantic_page, which collapses on
    a <main>-less SPA), each vision component's root element — resolved into THIS
    page's local-mirror DOM (via vision_extract) — is fed into the EXISTING
    decompose_group skeleton machinery, typed by the vision name via the manifest
    instanceTypeMap. Regions NOT covered by any vision component load as verbatim
    rawHtml (partition exactness). The whole body reconstructs BYTE-FOR-BYTE:
    each promoted region self-checks (recompose == original) and falls back to
    verbatim rawHtml on any mismatch (fidelity before contribution, rule 23).

    Segmented page  -> the page's own vision boundaries (vision_extract.resolve_segmented).
    Unsegmented     -> signature match against the segmented pages (match_unsegmented).
    Both promote through the identical path and self-check; no match -> verbatim."""
    import vision_extract as VE
    from bs4 import BeautifulSoup, NavigableString, Tag
    ov = overrides or {}
    base = ov.get("assetBase") or ""
    # contribution dial (G1): library kinds listed here skip LR promotion and
    # fall back to the SKELETON path, whose decompose lifts their text into
    # editable body fields. Library atoms keep text VERBATIM (title/image/link
    # only editable) — right for logoWall (no text), wrong for text-heavy
    # carousels/tabs (observed: 72% of a city page's visible text locked in
    # carousel verbatim). From overrides `noLibraryKinds` or the
    # EXTRACT_NO_LIBRARY_KINDS env (comma-separated), e.g. "carousel,tabs".
    no_lib_kinds = set(ov.get("noLibraryKinds")
                       or [s.strip() for s in
                           os.environ.get("EXTRACT_NO_LIBRARY_KINDS", "").split(",")
                           if s.strip()])
    itm = {k.lower(): v for k, v in ((manifest or {}).get("instanceTypeMap") or {}).items()}
    container_types = {c["nodeType"] for c in (manifest or {}).get("components", [])
                       if c.get("isContainer") and c.get("childType")}
    # P6.3: the project content namespace (asr) — the library recognizer emits
    # ns:logoWall / ns:logo etc. Derived from the manifest passthroughType.
    ns = ((manifest or {}).get("passthroughType") or "ns:x").split(":")[0]

    def lr_recognize(el):
        """LR.recognize gated by the noLibraryKinds contribution dial."""
        plan = LR.recognize(el, ns)
        if plan is not None and plan.get("kind") in no_lib_kinds:
            return None
        return plan

    def role_for(vision_name):
        # vision name -> role key present in instanceTypeMap (norm_name, the
        # cross-page id segment2manifest keys on). Falls back to the raw name.
        key = re.sub(r"[^A-Za-z0-9]+", "-", (vision_name or "").strip().lower()).strip("-")
        return key if key in itm else (vision_name or "component")

    def type_allows_items(role):
        return itm.get((role or "").lower()) in container_types

    def conv_media(med):
        return [{"name": m["name"], "orig": rewrite_asset_refs(m["orig"], base),
                 "file": filename_for(m["src"]), "alt": m.get("alt", "")}
                for m in (med or [])]

    def payload_extras(d):
        return {"media": conv_media(d.get("media")), "mediaTotal": d.get("mediaTotal", 0),
                "link": d.get("link"), "linkTotal": d.get("linkTotal", 0)}

    def rw_fields(flds):
        return {k: (rewrite_asset_refs(v, base) if k.startswith("body") else v)
                for k, v in flds.items()}

    def raw_instance(html, area=None):
        inst = {"type": "rawHtml", "parent": None, "passthrough": True,
                "fields": {"html": rewrite_asset_refs(html, base)},
                "images": [], "links": []}
        if area:
            inst["area"] = area
        return inst

    lift_stats = {"byteFail": 0, "emptyShell": 0, "libraryPromoted": 0}
    library_gaps = []   # (role, reason) — each rawHtml/skeleton fallback that a
                        # library recognizer COULD one day cover (feeds §5 growth)

    import semantic_extract as SE
    import library_recognize as LR

    def emit_library_plan(plan):
        """P6.3 GENERIC library promotion: a recognized DOM subtree -> a REAL
        composable container instance + N typed atom CHILD instances (parent
        linkage), library-native (no frozen skeleton). Every atom carries its
        SOURCE fidelity facts (verbatim media orig, source anchor class, href)
        so an unedited node is byte-exact (rule 26); the loader wires DAM weakref
        + jmix:externalLink. Returns the number of instances appended to `out`.

        This is the fidelity↔composability reconciliation applied generically:
        the container view reproduces the source wrapper classes; each child atom
        is fully editable (image + link) — the logo-wall debt (1/N editable) is
        gone for EVERY subtree the recognizer covers, not just the prototype one.
        """
        cont_idx = len(out)
        container = {
            "type": plan["kind"], "nodeType": plan["nodeType"],
            "parent": None, "libraryPlan": True, "promoted": True,
            "atomType": plan["atomType"],
            "container": plan["container"],
            "fields": {}, "images": [], "links": [],
        }
        out.append(container)
        n = 1

        def _atom(facts, name):
            return _library_atom(plan, cont_idx, facts, name, base)

        master = plan.get("master")
        if master:
            out.append(_atom(master, "master"))
            n += 1
        for i, facts in enumerate(plan.get("children") or [], 1):
            out.append(_atom(facts, f"item-{i}"))
            n += 1
        lift_stats["libraryPromoted"] += 1
        return n

    def raw_lifted_live(el):
        """LIVE passthrough element -> ANONYMOUS editable block (same P2.5
        mechanism as the semantic adapter's raw_lifted_instance). Operates on the
        LIVE mirror element so decompose_group's byte self-check (recompose ==
        str(el)) is honest — never a re-parsed string (fragment re-parse is not
        byte-idempotent on this AEM markup, ~24-char drift observed). Returns the
        lifted instance, or None when nothing was liftable / byte-check failed
        (caller keeps the region verbatim)."""
        if el is None:
            return None
        d = SE.decompose_group(el, allow_items=False, lift_titles=False)
        if not d["ok"]:
            lift_stats["byteFail"] += 1
            return None
        def _has(pl):
            return pl.get("fields") or pl.get("media") or pl.get("link")
        if not _has(d) and not any(_has(ch) for ch in d["children"]):
            return None
        # same child-marker contract as raw_lifted_instance: decompose can emit
        # {{child:N}} even with allow_items=False — carry the child payloads or
        # recompose renders holes (phantom markers).
        return {"type": "rawHtml", "parent": None, "passthrough": True,
                "fields": {k: rewrite_asset_refs(v, base) for k, v in d["fields"].items()},
                "skeleton": rewrite_asset_refs(d["skeleton"], base),
                "children": [{"fields": {k: rewrite_asset_refs(v, base)
                                         for k, v in ch["fields"].items()},
                              "skeleton": rewrite_asset_refs(ch["skeleton"], base),
                              **payload_extras(ch)} for ch in d["children"]],
                "skeletonSubs": sorted(d["fields"]) + sorted(
                    k for ch in d["children"] for k in ch["fields"]),
                "skeletonMissed": [],
                **payload_extras(d), "images": [], "links": []}

    def promote_live(vision_name, el):
        """Promote a LIVE vision component element (P4 + P6.3).

        FIDELITY-FIRST library recognition runs FIRST (MODULARITY-PLAN §5b): if the
        subtree maps onto a base-library pattern (logoWall/…), emit REAL composable
        typed atom child nodes (emit_library_plan) — returns (None, leaves) meaning
        'already appended to out'. Otherwise fall back to the P4 skeleton path
        (decompose_group, self-checked against str(el)), and on byte-fail/empty-shell
        to verbatim rawHtml. Composability rises with library coverage; fidelity
        never regresses (each atom carries its verbatim source markup)."""
        role = role_for(vision_name)
        original = str(el)
        # snapshot the leaf count BEFORE any mutation (decompose/recognize)
        try:
            _snap0 = _reparse_root(original)
            _leaves0 = SE._count_leaves(_snap0) if _snap0 is not None else 0
        except Exception:
            _leaves0 = 0
        # P6.3 GENERIC LIBRARY RECOGNIZER — try to map onto the base library.
        plan = lr_recognize(el)
        if plan is not None:
            emit_library_plan(plan)
            return None, _leaves0
        else:
            library_gaps.append((role, LR.library_gap_reason(el)))
        d = SE.decompose_group(el, allow_items=type_allows_items(role))
        if not d["ok"]:
            lift_stats["byteFail"] += 1
            return raw_instance(d["original"]), 0

        def _has(pl):
            return pl.get("fields") or pl.get("media") or pl.get("link")
        if not _has(d) and not any(_has(ch) for ch in d["children"]):
            lift_stats["emptyShell"] += 1
            return raw_instance(d["original"]), 0
        inst = {
            "type": role, "parent": None, "promoted": True,
            "fields": rw_fields(d["fields"]),
            "skeleton": rewrite_asset_refs(d["skeleton"], base),
            **payload_extras(d),
            "children": [{"fields": rw_fields(ch["fields"]),
                          "skeleton": rewrite_asset_refs(ch["skeleton"], base),
                          **payload_extras(ch)} for ch in d["children"]],
            "skeletonSubs": sorted(d["fields"]) + sorted(
                k for ch in d["children"] for k in ch["fields"]),
            "skeletonMissed": [], "images": [], "links": [],
        }
        # leaf count is taken BEFORE decompose mutates el; approximate via the
        # recomposed original (text content is stable) — use the original element
        # snapshot's leaf count instead (compute on a throwaway parse of original)
        try:
            snap = _reparse_root(original)
            leaves = SE._count_leaves(snap) if snap is not None else 0
        except Exception:
            leaves = 0
        return inst, leaves

    # ── resolve vision component + chrome roots into THIS page's mirror DOM ──
    mir = BeautifulSoup(txt, "lxml")
    body = mir.find("body")
    if body is None:
        return semantic_page(txt, slug, overrides, manifest)  # nothing to partition
    segmented = os.path.isfile(f"projects/{project}/workflow-output/segment/{slug}.segmentation.json") \
        and os.path.isfile(f"projects/{project}/workflow-output/segment/{slug}.dom.html")
    chrome_index = sig_index.get("_chrome") if isinstance(sig_index, dict) else None
    if segmented:
        vroots = VE.resolve_segmented(project, slug, mir)
        chrome = VE.resolve_chrome(project, slug, mir)
        match_mode = "own-segmentation"
    else:
        vroots = VE.match_unsegmented(
            {k: v for k, v in sig_index.items() if k != "_chrome"}, mir)
        chrome = VE.match_chrome_unsegmented(chrome_index or {}, mir)
        match_mode = "signature"

    # A chrome root must not overlap a content root — overlapping regions would
    # corrupt the byte-exact split. Drop any chrome root that contains, or sits
    # inside, a promoted content root (content wins; chrome is best-effort).
    content_els = [e for _, e in vroots]
    def _overlaps(e):
        return any(ce in e.descendants or e in ce.parents for ce in content_els)
    chrome = [(a, n, e) for (a, n, e) in chrome if not _overlaps(e)]

    # roots keyed by identity, tagged with their kind.
    root_kind = {}   # id(el) -> ("component", name) | ("chrome", area)
    for name, el in vroots:
        root_kind[id(el)] = ("component", name)
    for area, name, el in chrome:
        root_kind.setdefault(id(el), ("chrome", area))
    root_ids = set(root_kind)

    out = []
    promoted_leaves = demoted_leaves = 0
    n_chrome = 0

    def _emit_root(el):
        """Emit one resolved vision root as a self-contained BALANCED region
        (mutates el's live subtree). Byte-safe: decompose self-checks on str(el)."""
        nonlocal promoted_leaves, demoted_leaves, n_chrome
        kind, payload = root_kind[id(el)]
        if kind == "chrome":
            out.append(raw_instance(str(el), area=payload))
            n_chrome += 1
            return
        inst, lv = promote_live(payload, el)
        if inst is None:
            # library plan already appended (container + typed atoms) — composable
            promoted_leaves += lv
            return
        out.append(inst)
        if inst.get("promoted"):
            promoted_leaves += lv
        else:
            demoted_leaves += lv

    def _has_root_below(el):
        return any(id(d) in root_ids for d in el.descendants)

    def emit_container_live(el, inner_roots):
        """A root-bearing WRAPPER that isn't itself a single vision root becomes an
        anonymous ns:rawHtml CONTAINER skeleton with a {{child:N}} marker per vision
        root, plus N SEPARATELY-TYPED child instances (parent -> the container's out
        index). The wrapper's own markup + inter-root passthrough stays in the
        container skeleton. On LIVE, composeNode splices each JCR child (by
        getNodes() order == creation == document order) into its {{child:N}} slot;
        in EDIT each child renders via <Render node> for its own edit frame
        (skeletonRender.ts / rule 28). Each child keeps its VISION TYPE (heroBanner,
        newsCarousel, …) — per-component typing preserved.

        Balanced (the container is one complete element) and byte-exact
        (decompose_group_with_items self-checks recompose == str(el)); on any
        mismatch the whole wrapper loads verbatim (rule 23). Appends to `out`;
        returns the container's content-leaf count."""
        nonlocal promoted_leaves, demoted_leaves
        # keep only mutually non-nested roots (a nested root's marker would be
        # swallowed); VE.decompose_group_with_items also guards, mirror here for the
        # child-instance list to stay 1:1 with the {{child:N}} markers.
        inner = [r for r in inner_roots
                 if not any(o is not r and o in r.parents for o in inner_roots)]
        role_seq = []  # role per surviving root, in document order (== marker order)
        for r in inner:
            k = root_kind.get(id(r))
            role_seq.append(role_for(k[1]) if k and k[0] == "component" else "rawHtml")
        # vision-classified CHROME roots nested inside the wrapper (AEM SPA: header/
        # footer live in the content container). They load inline (byte-faithful)
        # but are tagged so contribution math treats them as chrome, not content —
        # nav/header text is tree-driven in Jahia, never contributor richtext.
        chrome_seq = [bool((root_kind.get(id(r)) or ("", ""))[0] == "chrome")
                      for r in inner]
        # P6.3: BEFORE decompose_group_with_items mutates the inner roots, try to
        # map each onto the base library (fidelity-first). A matched root becomes a
        # library-native COMPOSABLE child (logoWall + typed atoms) instead of a
        # frozen skeleton — while keeping its verbatim markup as the {{child:N}}
        # skeleton (byte-exact LIVE splice + self-check parity). Order == marker order.
        lib_plans = []
        for r in inner:
            k = root_kind.get(id(r))
            plan = lr_recognize(r) if (k and k[0] == "component") else None
            lib_plans.append(plan)
            if plan is None and k and k[0] == "component":
                library_gaps.append((role_for(k[1]), LR.library_gap_reason(r)))
        original = str(el)
        snap = _reparse_root(original)
        leaves = SE._count_leaves(snap) if snap is not None else 0
        d = VE.decompose_group_with_items(el, inner, lift_titles=False)
        if not d["ok"]:
            lift_stats["byteFail"] += 1
            out.append(raw_instance(d["original"]))
            demoted_leaves += leaves
            return
        cont_idx = len(out)
        out.append({
            "type": "rawHtml", "parent": None, "promoted": True, "container": True,
            "fields": {k: rewrite_asset_refs(v, base) for k, v in d["fields"].items()},
            "skeleton": rewrite_asset_refs(d["skeleton"], base),
            **payload_extras(d),
            "skeletonSubs": sorted(d["fields"]), "skeletonMissed": [],
            "images": [], "links": [],
        })
        # one child instance per {{child:N}} marker, in order. A child that lifted
        # NOTHING (a script-driven widget: booking bar, chatbot — no contributor
        # text/media/link) would be an empty typed shell (lies to the editor), so
        # it loads as an honest rawHtml passthrough child carrying its verbatim
        # markup — still spliced into its {{child:N}} slot, byte-identical.
        def _has(pl):
            return pl.get("fields") or pl.get("media") or pl.get("link")

        def _emit_library_child(plan, ch):
            """A library-matched inner root -> a COMPOSABLE library container child
            (logoWall) with its typed atom grandchildren. It ALSO carries the root's
            verbatim `skeleton` so the wrapper's {{child:N}} splice stays byte-exact
            on LIVE (rule 26 verbatim default); in EDIT the container renders via its
            library view (the atoms get their own edit frames, rule 28). Appends the
            container + N atoms to `out`."""
            lib_idx = len(out)
            out.append({
                "type": plan["kind"], "nodeType": plan["nodeType"],
                "parent": cont_idx, "libraryPlan": True, "promoted": True,
                "atomType": plan["atomType"], "container": plan["container"],
                # verbatim root markup -> byte-exact {{child:N}} splice on LIVE.
                # ch["skeleton"] is the TEMPLATED skeleton (decompose already moved
                # the field values into ch["fields"]) — storing it with fields={}
                # rendered literal {{f:*}} holes. Recompose it back to verbatim.
                "skeleton": rewrite_asset_refs(
                    SE.recompose_group(ch["skeleton"], ch.get("fields") or {}, [],
                                       media=ch.get("media"), link=ch.get("link")),
                    base),
                "skeletonSubs": [], "skeletonMissed": [],
                "fields": {}, "images": [], "links": [],
            })

            if plan.get("master"):
                out.append(_library_atom(plan, lib_idx, plan["master"], "master", base))
            for i, facts in enumerate(plan.get("children") or [], 1):
                out.append(_library_atom(plan, lib_idx, facts, f"item-{i}", base))
            lift_stats["libraryPromoted"] += 1

        for n, ch in enumerate(d["children"]):
            role = role_seq[n] if n < len(role_seq) else "rawHtml"
            if n < len(lib_plans) and lib_plans[n] is not None:
                _emit_library_child(lib_plans[n], ch)
                continue
            if not _has(ch):
                lift_stats["emptyShell"] += 1
                # rawHtml passthrough child, but carry a marker-free `skeleton` so
                # composeNode still splices it into {{child:N}} (it only splices
                # children with a skeleton prop) — recompose of a marker-free
                # skeleton == its verbatim markup, byte-identical on LIVE + EDIT.
                out.append({
                    "type": "rawHtml", "parent": cont_idx, "passthrough": True,
                    "chromeNested": (chrome_seq[n] if n < len(chrome_seq) else False),
                    "fields": {}, "skeleton": rewrite_asset_refs(ch["skeleton"], base),
                    "skeletonSubs": [], "skeletonMissed": [],
                    "media": [], "mediaTotal": 0, "link": None, "linkTotal": 0,
                    "images": [], "links": [],
                })
                continue
            out.append({
                "type": role, "parent": cont_idx, "promoted": True,
                "chromeNested": (chrome_seq[n] if n < len(chrome_seq) else False),
                "fields": rw_fields(ch["fields"]),
                "skeleton": rewrite_asset_refs(ch["skeleton"], base),
                **payload_extras(ch),
                "skeletonSubs": sorted(ch["fields"]), "skeletonMissed": [],
                "images": [], "links": [],
            })
        promoted_leaves += leaves

    # ── byte-exact partition; every emitted region is a COMPLETE balanced element
    # (the RawHtml renderer's splitRoot invariant — same as the semantic adapter's
    # topLevels). Walk body's direct children in document order:
    #   NOTE: chrome roots nested INSIDE the shared content wrapper (as on this AEM
    #   SPA, where header/footer live within container-structure) become rawHtml
    #   children of the container rather than area singletons — byte-faithful to the
    #   source (they render inline where the source renders them). Chrome routed to
    #   /home/<area> only when it is a top-level body sibling (the common case).
    #   * a resolved vision/chrome root -> promote/chrome directly (typed)
    #   * a wrapper bearing vision roots deeper -> ONE rawHtml container skeleton +
    #     per-root TYPED child instances ({{child:N}}; balanced + byte-exact)
    #   * a root-free wrapper -> lift text runs live | verbatim
    #   * a text node (incl. whitespace) -> verbatim (bytes contract)
    from bs4 import Comment
    for child in list(body.children):
        if not isinstance(child, Tag):
            # bs4 str(Comment) yields the BARE text — the <!-- --> markers must be
            # re-wrapped or comment content becomes VISIBLE text and the page body
            # is no longer byte-exact (rule 32; same fix as page_shell's ser()).
            t = f"<!--{child}-->" if isinstance(child, Comment) else str(child)
            if t:  # preserve ALL text incl. whitespace (bytes contract)
                out.append(raw_instance(t))
            continue
        if id(child) in root_ids:
            _emit_root(child)
            continue
        if _has_root_below(child):
            inner = [d for d in child.descendants
                     if isinstance(d, Tag) and id(d) in root_ids]
            emit_container_live(child, inner)
            continue
        out.append(raw_lifted_live(child) or raw_instance(str(child)))

    # empty-leaf accounting for the loader (containers keep, empty leaves flagged).
    # Library atoms carry their content in imageFile/imgOrig/href (not fields/
    # images/links) — they are NEVER empty (a real editable node the loader wires).
    parents = {i["parent"] for i in out if i.get("parent") is not None}
    for idx, i in enumerate(out):
        if i.get("libraryPlan") or i.get("libraryAtom"):
            i["empty"] = False
            continue
        i["empty"] = not (i["fields"] or i["images"] or i["links"]) and idx not in parents

    shell = page_shell(txt, base) if ov.get("shell", True) else None

    # accounting parity with semantic_page's partition summary (probe reads these)
    total_leaves = _vision_body_leaves(txt)
    n_promoted = sum(1 for i in out if i.get("promoted"))
    # Every body child is emitted as at least one instance (promoted, container,
    # lifted, or verbatim raw) — partition is total by construction.
    summary = {
        "adapterMode": "vision",
        "matchMode": match_mode,
        "visionComponents": len(vroots),
        "chromeAreas": n_chrome,
        "leavesTotal": total_leaves,
        "leavesCovered": total_leaves,
        "semanticLeafShare": round(promoted_leaves / total_leaves, 3) if total_leaves else None,
        "demotedLeaves": demoted_leaves,
        "liftByteFail": lift_stats["byteFail"],
        "liftEmptyShell": lift_stats["emptyShell"],
        # P6.3 library promotion: containers promoted onto the base library + the
        # typed atom children (composable, no frozen skeleton). library gaps = the
        # roots that fell back to skeleton/rawHtml (feeds library growth §5).
        "libraryPromoted": lift_stats["libraryPromoted"],
        "libraryAtoms": sum(1 for i in out if i.get("libraryAtom")),
        "libraryGaps": len(library_gaps),
        # vision children are SEPARATE parent-referenced instances (typed per
        # component), not embedded — count them by parent linkage.
        "childItems": sum(1 for i in out if i.get("parent") is not None),
        "containerRegions": sum(1 for i in out if i.get("container")),
        "componentRegions": n_promoted,
        "passthroughRegions": sum(1 for i in out if i.get("passthrough") and not i.get("area")),
    }
    if library_gaps:
        # keep a compact reason histogram so the fallback tail is legible
        from collections import Counter as _C
        summary["libraryGapReasons"] = dict(_C(r for _, r in library_gaps))
    page = {"adapter": "semantic", "instances": out, "partition": summary}
    if shell:
        page["shell"] = shell
    return page


def _vision_body_leaves(txt):
    """Content-leaf count of the whole body (accounting denominator for the vision
    partition, which has no <main>). Uses semantic_extract._count_leaves."""
    from bs4 import BeautifulSoup
    import semantic_extract as SE
    soup = BeautifulSoup(txt, "lxml")
    body = soup.find("body")
    return SE._count_leaves(body) if body is not None else 0


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: extract_content.py <project> [site_key] [--adapter semantic|sxa]")
    project = sys.argv[1]
    # P3: the SEMANTIC adapter (shell + skeleton + per-item contribution) is THE
    # v2 architecture for every source CMS — SXA is just another HTML renderer.
    # The v1 SXA adapter stays available behind --adapter sxa for the legacy
    # reference modules only.
    force_sxa = "--adapter" in sys.argv and "sxa" in sys.argv
    proj = f"projects/{project}"
    global _DATA_URI_DIR
    _DATA_URI_DIR = os.path.join(proj, "workflow-output", "local-mirror", "assets")
    if not os.path.isdir(_DATA_URI_DIR):
        _DATA_URI_DIR = None
    pages = captured_pages(proj)
    if not pages:
        sys.exit(f"extract_content: no captured pages under {proj}/.reference")

    load_runtime_map(project)
    load_media_map(project)
    overrides = load_overrides(project)
    if overrides:
        print(f"extract_content: passthrough overrides active — demoteRoles="
              f"{overrides.get('demoteRoles')}, chromePassthrough="
              f"{overrides.get('chromePassthrough')}, assetBase={overrides.get('assetBase')}")
    try:  # P2.5: childType awareness — items become child nodes only when typed
        manifest = json.load(open(f"projects/{project}/workflow-output/component-manifest.json"))
    except Exception:
        manifest = None

    # Adapter selection is AUTOMATIC (P4), and SELF-SELECTING so committed baselines
    # never move: the VISION adapter engages ONLY when (a) passing vision
    # segmentations exist AND (b) the independent semantic walk COLLAPSES on this
    # site — i.e. extract_page finds ~0 component regions across the sampled pages
    # (the exact <main>-less-SPA failure the bridge exists for: discoverasr 0/1631).
    # Sites where the semantic adapter already works (acquia/supercar/contentful,
    # 8-13 component regions/page) keep the semantic path byte-identical — no flag,
    # no per-site config. force_sxa (legacy) always wins.
    use_vision = False
    sig_index = {}
    if not force_sxa and manifest:
        try:
            import vision_extract as VE
            if VE.has_vision_segmentations(project):
                sem_comp = 0
                sampled = 0
                for _slug, _path, _b in pages[:5]:
                    try:
                        _t = open(_path, encoding="utf-8", errors="ignore").read()
                        _, _c, _part = __import__("semantic_extract").extract_page(_t, _slug)
                        sem_comp += _part.get("componentRegions", 0)
                        sampled += 1
                    except Exception:
                        continue
                if sampled and sem_comp == 0:
                    use_vision = True
                    sig_index = VE.load_signature_index(project)
                    sig_index["_chrome"] = VE.load_chrome_signatures(project)
                    print(f"extract_content: semantic walk collapsed (0 component "
                          f"regions / {sampled} pages) -> VISION adapter | "
                          f"{len(sig_index) - 1} component + {len(sig_index['_chrome'])} "
                          f"chrome signature(s) learned from segmented pages")
                else:
                    print(f"extract_content: semantic walk healthy ({sem_comp} "
                          f"component regions / {sampled} pages) -> keeping semantic "
                          f"adapter (vision segmentations present but not needed)")
        except ImportError:
            pass

    data = {"adapter": None, "pages": {}}
    sxa_pages = sem_pages = vis_pages = 0
    vis_match_log = []
    for slug, path, _ in pages:
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except Exception as e:
            print(f"  ! {slug}: {e}", file=sys.stderr)
            continue
        if force_sxa and detect_sxa(txt):
            p = SXAContent()
            p.feed(txt)
            # distribute a grid container's images to its item children positionally:
            # picture-grids render the card image in a sibling `.card-img`, so the
            # images land on the parent in order while the text lands on the cards.
            kids_of = {}
            for j, inst in enumerate(p.instances):
                if inst.get("parent") is not None:
                    kids_of.setdefault(inst["parent"], []).append(j)
            for pi, kids in kids_of.items():
                items = [k for k in kids if p.instances[k].get("item")]
                par = p.instances[pi]
                if items and par["images"] and all(not p.instances[k]["images"] for k in items):
                    for n, k in enumerate(items):
                        if n < len(par["images"]):
                            p.instances[k]["images"].append(par["images"][n])
                    par["images"] = par["images"][len(items):]  # keep any extras on parent
            # keep ALL instances (stable indices for `parent` refs) — flag which are
            # empty leaves so the loader can skip them while preserving containers.
            parents = {i["parent"] for i in p.instances if i.get("parent") is not None}
            for idx, i in enumerate(p.instances):
                i["empty"] = not (i["fields"] or i["images"] or i["links"]) and idx not in parents
            data["pages"][slug] = {"adapter": "sxa", "instances": p.instances}
            sxa_pages += 1
        elif use_vision:
            try:
                pg = vision_page(project, txt, slug, sig_index, overrides, manifest)
                data["pages"][slug] = pg
                vis_pages += 1
                part = pg.get("partition", {})
                vis_match_log.append((slug, part.get("matchMode", "?"),
                                      part.get("visionComponents", 0),
                                      part.get("componentRegions", 0)))
            except ImportError:
                p = GenericContent()
                p.feed(txt)
                data["pages"][slug] = {"adapter": "generic", "blocks": p.blocks}
        else:
            try:
                data["pages"][slug] = semantic_page(txt, slug, overrides, manifest)
                sem_pages += 1
            except ImportError:
                # bs4 unavailable: legacy ordered-blocks fallback (NOT loadable by
                # load_content — instances only). Kept as a last-resort inspection aid.
                p = GenericContent()
                p.feed(txt)
                data["pages"][slug] = {"adapter": "generic", "blocks": p.blocks}
    # vision pages emit adapter:"semantic" (the contribution gate targets it), so
    # they count toward the semantic verdict.
    data["adapter"] = ("sxa" if sxa_pages > len(pages) / 2
                       else "semantic" if (sem_pages or vis_pages) else "generic")

    os.makedirs("orchestration/content", exist_ok=True)
    outp = f"orchestration/content/{project}.content-load.json"
    json.dump(data, open(outp, "w"), indent=2, ensure_ascii=False)
    # summary
    tot_inst = sum(len(v.get("instances", [])) for v in data["pages"].values())
    tot_text = sum(sum(len(f) for i in v.get("instances", []) for f in i["fields"].values())
                   for v in data["pages"].values())
    typed = sum(1 for v in data["pages"].values() for i in v.get("instances", []) if i.get("promoted"))
    anon = sum(1 for v in data["pages"].values() for i in v.get("instances", []) if i.get("skeleton") and not i.get("promoted"))
    raw = sum(1 for v in data["pages"].values() for i in v.get("instances", []) if i.get("passthrough"))
    print(f"extract_content: adapter={data['adapter']} | {len(pages)} pages "
          f"({vis_pages} vision, {sem_pages} semantic, {sxa_pages} sxa) | "
          f"{tot_inst} instances | {tot_text} chars real field text -> {outp}")
    print(f"  census: typed(promoted)={typed} anon-lifted-raw={anon} verbatim-raw={raw}")
    if vis_match_log:
        print("  vision per-page match counts (mode / vision-comps / promoted):")
        for slug, mode, nc, np in vis_match_log:
            print(f"    {slug:30s} {mode:16s} {nc:2d} -> {np:2d} promoted")


if __name__ == "__main__":
    main()
