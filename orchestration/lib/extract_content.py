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


def filename_for(url):
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


def rewrite_asset_refs(html, base):
    """Mirror markup references assets RELATIVELY (`assets/<hash>`) — valid at
    the mirror root, broken under /sites/... Rewrite to the module's static
    mirror copy (assetBase, e.g. /modules/<m>/static/)."""
    if not base or not html:
        return html
    return _ASSET_REF_RE.sub(lambda m: base + m.group(2), html)


def load_overrides(project):
    """workflow-output/passthrough-overrides.json — the P1 fidelity/semantic
    DIAL: {"demoteRoles": ["*"|role...], "chromePassthrough": bool,
    "assetBase": "/modules/<m>/static/"}. Demoted component regions load as
    verbatim rawHtml; promotion = removing roles as views become exact."""
    p = f"projects/{project}/workflow-output/passthrough-overrides.json"
    try:
        return json.load(open(p))
    except Exception:
        return {}


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
        return None

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
    p = main.parent
    anc = []
    while p is not None and p is not body:
        anc.append(p)
        p = p.parent
    chain += list(reversed(anc))  # body, wrapper1, ..., main.parent

    def chunk(parts):
        html = _EXT_SCRIPT_RE.sub("", rewrite_asset_refs("".join(parts), base))
        return html.strip()

    levels = []
    for i, node in enumerate(chain):
        nxt = chain[i + 1] if i + 1 < len(chain) else main
        before, after, seen = [], [], False
        for child in node.children:
            if child is nxt:
                seen = True
                continue
            (after if seen else before).append(str(child))
        levels.append({
            "tag": node.name if node is not body else "body",
            "attrs": _attrs_of(node),
            "before": chunk(before),
            "after": chunk(after),
        })
    return {
        "bodyAttrs": _attrs_of(body),
        "mainAttrs": _attrs_of(main),
        "levels": levels,
        "head": head_items,
    }


def semantic_page(txt, slug, overrides=None):
    """v2 adapter: reuse semantic_extract's deterministic component walk so each
    instance's `type` is the same ROLE the manifest's instanceTypeMap keys on —
    the whole point of the bridge (load_content resolves role -> ns:nodeType).

    Emits load-shaped instances with parents always preceding their children.
    Main-region instances follow the P1.2 partition in DOCUMENT ORDER, with
    uncovered regions emitted as `rawHtml` passthrough instances — every content
    leaf of <main> reaches the JCR exactly once (the ≥99 % fidelity invariant).

    Overrides (P1 dial): demoted roles load as verbatim rawHtml; chrome
    (header/nav/footer) can load as area-flagged rawHtml singletons."""
    from semantic_extract import extract_page  # bs4/lxml — pipeline dependency
    ov = overrides or {}
    demote = set(ov.get("demoteRoles") or [])
    demote_all = "*" in demote
    chrome_pass = bool(ov.get("chromePassthrough"))
    base = ov.get("assetBase") or ""
    _, comps, partition = extract_page(txt, slug)
    out, remap = [], {}

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

    # chrome (header/footer/nav — routed to absolute areas by the loader) and any
    # off-main components first; then <main> strictly in document order
    for i in range(len(comps)):
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
        return not (demote_all or role in demote)

    demoted_leaves = 0
    for ti in sorted(by_top.keys()):
        group = by_top[ti]
        promoted = [r for r in group if region_promoted(r)]
        if not promoted and 0 <= ti < len(top_levels):
            out.append(raw_instance(top_levels[ti]["html"]))
            demoted_leaves += sum(r.get("leaves", 0) for r in group
                                  if r["kind"] == "component")
            for r in group:
                if r.get("compIndex") is not None:
                    for j in subtree(r["compIndex"]):
                        remap[j] = None
            continue
        for r in group:
            if r["kind"] == "component":
                ci = r.get("compIndex")
                if ci is None:
                    continue
                if region_promoted(r):
                    for j in subtree(ci):
                        emit(j)
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
    summary = {k: v for k, v in partition.items() if k != "regions"}
    if demoted_leaves:
        total = summary.get("leavesTotal") or 0
        sem = sum(r.get("leaves", 0) for r in regions if r["kind"] == "component"
                  and r.get("compIndex") is not None
                  and not (demote_all or comps[r["compIndex"]]["role"] in demote))
        summary["semanticLeafShare"] = round(sem / total, 3) if total else None
        summary["demotedLeaves"] = demoted_leaves
    n_comp = sum(1 for i in out if not i.get("passthrough") and i.get("parent") is None
                 and not i.get("area"))
    summary["componentRegions"] = n_comp
    summary["passthroughRegions"] = sum(1 for i in out if i.get("passthrough") and not i.get("area"))
    page = {"adapter": "semantic", "instances": out, "partition": summary}
    if shell:
        page["shell"] = shell
    return page


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: extract_content.py <project> [site_key]")
    project = sys.argv[1]
    proj = f"projects/{project}"
    pages = captured_pages(proj)
    if not pages:
        sys.exit(f"extract_content: no captured pages under {proj}/.reference")

    overrides = load_overrides(project)
    if overrides:
        print(f"extract_content: passthrough overrides active — demoteRoles="
              f"{overrides.get('demoteRoles')}, chromePassthrough="
              f"{overrides.get('chromePassthrough')}, assetBase={overrides.get('assetBase')}")
    data = {"adapter": None, "pages": {}}
    sxa_pages = sem_pages = 0
    for slug, path, _ in pages:
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except Exception as e:
            print(f"  ! {slug}: {e}", file=sys.stderr)
            continue
        if detect_sxa(txt):
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
        else:
            try:
                data["pages"][slug] = semantic_page(txt, slug, overrides)
                sem_pages += 1
            except ImportError:
                # bs4 unavailable: legacy ordered-blocks fallback (NOT loadable by
                # load_content — instances only). Kept as a last-resort inspection aid.
                p = GenericContent()
                p.feed(txt)
                data["pages"][slug] = {"adapter": "generic", "blocks": p.blocks}
    data["adapter"] = ("sxa" if sxa_pages > len(pages) / 2
                       else "semantic" if sem_pages else "generic")

    os.makedirs("orchestration/content", exist_ok=True)
    outp = f"orchestration/content/{project}.content-load.json"
    json.dump(data, open(outp, "w"), indent=2, ensure_ascii=False)
    # summary
    tot_inst = sum(len(v.get("instances", [])) for v in data["pages"].values())
    tot_text = sum(sum(len(f) for i in v.get("instances", []) for f in i["fields"].values())
                   for v in data["pages"].values())
    print(f"extract_content: adapter={data['adapter']} | {len(pages)} pages | "
          f"{tot_inst} component instances | {tot_text} chars of real field text -> {outp}")
    for slug, v in list(data["pages"].items())[:8]:
        n = len(v.get("instances", v.get("blocks", [])))
        print(f"  {slug:28s} {v['adapter']:8s} {n} {'blocks' if v['adapter'] == 'generic' else 'instances'}")


if __name__ == "__main__":
    main()
