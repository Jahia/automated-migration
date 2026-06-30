#!/usr/bin/env python3
"""extract_content.py — DETERMINISTIC, SOURCE-AGNOSTIC content harvest.

The real content (titles, copy, dates, card text, article bodies, links) lives in
the captured DOM. The old pipeline asked the LLM to "create content" via MCP and
it improvised placeholder/empty results. This extracts the REAL content per page
into content-data.json, which the content step then LOADS into the JCR (the LLM
only maps ambiguous cases, it does not invent text).

Agnostic by design — every CMS renders to HTML:
  * SXA adapter (Sitecore): each `.component > .component-content` is an instance;
    each `field-<name>` is a property value. Precise; used by the 3 current sites.
  * generic adapter (Drupal / WordPress / AEM / plain HTML): walk the main content
    region and emit the ordered block sequence (headings / text / images / links).

Image references are resolved to the filenames produced by extract_media.py, so
the content step can wire the imported DAM nodes.

Usage: python3 orchestration/lib/extract_content.py <project> [site_key]
Writes: orchestration/content/<project>.content-data.json
"""
import html.parser, json, os, re, sys, urllib.parse

IMG_EXT = re.compile(r"\.(png|jpe?g|webp|gif|svg|avif)(\?|$)", re.I)
LAYOUT = re.compile(r"^(component|component-content|container|container-fluid|row|"
                    r"col|col-\w+|mb-\d+|mt-\d+|p-\d+|px-\d+|py-\d+|g-\d+|gap-\d+|"
                    r"d-\w+|text-\w+|fw-\w+|fs-\w+|w-\d+|h-\d+|align-\w+|justify-\w+)$")


def captured_pages(proj):
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
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.instances = []
        self.compstack = []          # (instance_idx, divdepth)
        self.divdepth = 0
        self.fieldstack = []         # (instance_idx, fieldname, divdepth)
        self.in_a = None             # (instance_idx, href, text_parts)

    def _start_component(self, toks):
        after = [t for t in toks if not LAYOUT.match(t)]
        ctype = after[0] if after else "unknown"
        # parent = the enclosing component instance (top of the stack), if any —
        # this preserves container nesting (carousel -> slides, tabs -> items) the
        # loader needs to recreate the JCR hierarchy instead of a flat list.
        parent = self.compstack[-1][0] if self.compstack else None
        self.instances.append({"type": ctype, "parent": parent,
                               "fields": {}, "images": [], "links": []})
        self.compstack.append((len(self.instances) - 1, self.divdepth))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        toks = (a.get("class") or "").split()
        if tag == "div":
            self.divdepth += 1
            if "component" in toks and "component-content" not in toks:
                self._start_component(toks)
        if not self.compstack:
            return
        cur = self.compstack[-1][0]
        # field-<name> element -> capture its text into fields[name]
        for t in toks:
            if t.startswith("field-"):
                self.fieldstack.append((cur, t[len("field-"):], self.divdepth))
        # images inside this component
        if tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src and IMG_EXT.search(src) and not src.startswith("data:"):
                self.instances[cur]["images"].append(
                    {"file": filename_for(src), "alt": clean(a.get("alt", ""))})
        # links inside this component
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


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: extract_content.py <project> [site_key]")
    project = sys.argv[1]
    proj = f"projects/{project}"
    pages = captured_pages(proj)
    if not pages:
        sys.exit(f"extract_content: no captured pages under {proj}/.reference")

    data = {"adapter": None, "pages": {}}
    sxa_pages = 0
    for slug, path, _ in pages:
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except Exception as e:
            print(f"  ! {slug}: {e}", file=sys.stderr)
            continue
        if detect_sxa(txt):
            p = SXAContent()
            p.feed(txt)
            # keep ALL instances (stable indices for `parent` refs) — flag which are
            # empty leaves so the loader can skip them while preserving containers.
            parents = {i["parent"] for i in p.instances if i.get("parent") is not None}
            for idx, i in enumerate(p.instances):
                i["empty"] = not (i["fields"] or i["images"] or i["links"]) and idx not in parents
            data["pages"][slug] = {"adapter": "sxa", "instances": p.instances}
            sxa_pages += 1
        else:
            p = GenericContent()
            p.feed(txt)
            data["pages"][slug] = {"adapter": "generic", "blocks": p.blocks}
    data["adapter"] = "sxa" if sxa_pages > len(pages) / 2 else "generic"

    os.makedirs("orchestration/content", exist_ok=True)
    outp = f"orchestration/content/{project}.content-data.json"
    json.dump(data, open(outp, "w"), indent=2, ensure_ascii=False)
    # summary
    tot_inst = sum(len(v.get("instances", [])) for v in data["pages"].values())
    tot_text = sum(sum(len(f) for i in v.get("instances", []) for f in i["fields"].values())
                   for v in data["pages"].values())
    print(f"extract_content: adapter={data['adapter']} | {len(pages)} pages | "
          f"{tot_inst} component instances | {tot_text} chars of real field text -> {outp}")
    for slug, v in list(data["pages"].items())[:8]:
        n = len(v.get("instances", v.get("blocks", [])))
        print(f"  {slug:28s} {v['adapter']:8s} {n} {'instances' if v['adapter']=='sxa' else 'blocks'}")


if __name__ == "__main__":
    main()
