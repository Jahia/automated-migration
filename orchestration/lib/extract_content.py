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
        out = [(p["slug"], os.path.join(proj, p["cachedAt"]), None)
               for p in pages if p.get("slug") and p.get("cachedAt")
               and os.path.isfile(os.path.join(proj, p["cachedAt"]))]
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


def semantic_page(txt, slug):
    """v2 adapter: reuse semantic_extract's deterministic component walk so each
    instance's `type` is the same ROLE the manifest's instanceTypeMap keys on —
    the whole point of the bridge (load_content resolves role -> ns:nodeType).
    Emits load-shaped instances: parents always precede their children."""
    from semantic_extract import extract_page  # bs4/lxml — pipeline dependency
    _, comps = extract_page(txt, slug)
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

    for i in range(len(comps)):
        emit(i)
    parents = {i["parent"] for i in out if i.get("parent") is not None}
    for idx, i in enumerate(out):
        i["empty"] = not (i["fields"] or i["images"] or i["links"]) and idx not in parents
    return {"adapter": "semantic", "instances": out}


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: extract_content.py <project> [site_key]")
    project = sys.argv[1]
    proj = f"projects/{project}"
    pages = captured_pages(proj)
    if not pages:
        sys.exit(f"extract_content: no captured pages under {proj}/.reference")

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
                data["pages"][slug] = semantic_page(txt, slug)
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
