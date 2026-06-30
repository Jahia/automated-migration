#!/usr/bin/env python3
"""extract_media.py — DETERMINISTIC, SOURCE-AGNOSTIC media harvest.

Every CMS (Sitecore, Drupal, WordPress, AEM, plain HTML) serves rendered HTML, so
the captured DOM is the universal source of truth for media. This walks every
captured page and emits the per-page image manifest the existing importer
(orchestration/images/import.py) consumes — replacing the LLM-authored manifest
that was incomplete/absent (the "0 of 40 images" failure).

It is pure stdlib HTML parsing (no CMS assumptions, no pip deps): it harvests
  <img src>, <img data-src> (lazy), srcset (largest candidate), <source srcset>,
  <link rel=*icon* href>, <meta property=og:image>, and url(...) in style="" / <style>.
Relative URLs resolve against the captured origin. A best-effort role
(logo/hero/banner/partner/icon/content) is inferred from the URL path + alt/class
so downstream wiring can place each image.

Usage:
  python3 orchestration/lib/extract_media.py <project> [site_key]
Writes: orchestration/images/<project>.json  (consumed by images/import.py)
"""
import html.parser, json, os, re, sys, urllib.parse

IMG_EXT = re.compile(r"\.(png|jpe?g|webp|gif|svg|avif)(\?|$)", re.I)
# Order matters: more specific / context-winning hints first. Partner/sponsor must
# beat "logo" (partner logos live at .../partenaires/logo-xyz.png and would
# otherwise all be mislabeled as the brand logo).
ROLE_HINTS = [
    ("favicon", "icon"), ("partenaire", "partner"), ("partner", "partner"),
    ("sponsor", "partner"), ("exposant", "partner"),
    ("hero", "hero"), ("key-visual", "hero"), ("slide", "hero"), ("banner", "banner"),
    ("logo-salon", "logo"), ("logo-site", "logo"), ("brand", "logo"),
    ("actu", "card"), ("news", "card"), ("card", "card"), ("vignette", "card"),
    ("thumb", "card"), ("teaser", "card"),
    ("icon", "icon"), ("logo", "partner"),  # a bare "logo" with no brand marker is most often a partner logo
]


def role_for(url, alt, cls):
    hay = f"{url} {alt} {cls}".lower()
    for needle, role in ROLE_HINTS:
        if needle in hay:
            return role
    return "content"


def largest_srcset(srcset):
    # "a.jpg 480w, b.jpg 2000w" -> pick the highest w/x descriptor (or first)
    best, best_n = None, -1
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        u = bits[0]
        n = 0
        if len(bits) > 1:
            m = re.match(r"(\d+)[wx]", bits[1])
            n = int(m.group(1)) if m else 0
        if n >= best_n:
            best, best_n = u, n
    return best


class MediaParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hits = []  # (url, alt, cls)

    def _add(self, url, alt="", cls=""):
        if url and not url.startswith("data:"):
            self.hits.append((url.strip(), alt, cls))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "img":
            alt = a.get("alt", "")
            # prefer real src over a lazy/placeholder; also take data-src/data-original
            for key in ("src", "data-src", "data-original", "data-lazy-src"):
                if a.get(key):
                    self._add(a[key], alt, cls)
            if a.get("srcset"):
                self._add(largest_srcset(a["srcset"]), alt, cls)
        elif tag == "source" and a.get("srcset"):
            self._add(largest_srcset(a["srcset"]), "", cls)
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if "icon" in rel and a.get("href"):
                self._add(a["href"], "", "favicon")
        elif tag == "meta":
            if (a.get("property") or a.get("name") or "").lower() in ("og:image", "twitter:image") and a.get("content"):
                self._add(a["content"], "", "og")
        # inline background-image
        style = a.get("style", "")
        for m in re.finditer(r"url\(([^)]+)\)", style):
            self._add(m.group(1).strip("'\" "), "", cls)

    def handle_data(self, data):
        # url(...) inside <style> blocks (best-effort; many themes inline bg images)
        if "url(" in data and len(data) < 200000:
            for m in re.finditer(r"url\(([^)]+)\)", data):
                u = m.group(1).strip("'\" ")
                if IMG_EXT.search(u):
                    self._add(u)


def captured_pages(proj):
    """Return [(slug, html_path, origin_base)] from the capture layer (agnostic)."""
    out = []
    capdir = f"{proj}/.reference/captured"
    if os.path.isdir(capdir):
        for fn in sorted(os.listdir(capdir)):
            if fn.endswith(".html"):
                out.append((fn[:-5], os.path.join(capdir, fn), None))
        if out:
            return out
    # fall back to the wget crawl cache: .reference/cache/_crawl/<host>/<path>.html
    crawl = f"{proj}/.reference/cache/_crawl"
    for dp, _, fs in os.walk(crawl):
        for fn in fs:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, crawl)
            parts = rel.split(os.sep)
            host = parts[0]
            base = f"https://{host}"
            sub = "/".join(parts[1:])[:-5]  # strip .html
            # <lang>.html at root -> home; <lang>/<slug> -> last segment
            slug = "home" if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", sub) else sub.split("/")[-1]
            out.append((slug, p, base))
    return out


def filename_for(url):
    path = urllib.parse.urlparse(url).path
    name = os.path.basename(path) or "image"
    name = urllib.parse.unquote(name)
    if not IMG_EXT.search(name):
        name += ".img"
    return re.sub(r"[^A-Za-z0-9._-]", "-", name)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: extract_media.py <project> [site_key]")
    project = sys.argv[1]
    site = sys.argv[2] if len(sys.argv) > 2 else project
    proj = f"projects/{project}"
    pages = captured_pages(proj)
    if not pages:
        sys.exit(f"extract_media: no captured pages under {proj}/.reference "
                 f"(run capture-reference first)")

    origin = None
    manifest = {"base": "", "destRoot": f"/sites/{site}/files/migrated-media", "pages": {}}
    seen_global = set()
    total = 0
    for slug, path, base in pages:
        if base and not origin:
            origin = base
        parser = MediaParser()
        try:
            parser.feed(open(path, encoding="utf-8", errors="ignore").read())
        except Exception as e:
            print(f"  ! {slug}: parse error {e}", file=sys.stderr)
            continue
        imgs, by_file = [], {}
        for url, alt, cls in parser.hits:
            absu = urllib.parse.urljoin((base or origin or "") + "/", url)
            if not IMG_EXT.search(absu):
                continue
            fn = filename_for(absu)
            # dedup by filename (src + srcset + responsive variants are the same asset);
            # keep the largest variant (highest w= query) so the import gets full-res.
            w = 0
            m = re.search(r"[?&]w=(\d+)", absu)
            if m:
                w = int(m.group(1))
            prev = by_file.get(fn)
            if prev and prev["_w"] >= w:
                continue
            rec = {"src": absu, "file": fn, "role": role_for(absu, alt, cls), "alt": alt, "_w": w}
            by_file[fn] = rec
        imgs = [{k: v for k, v in r.items() if k != "_w"} for r in by_file.values()]
        if imgs:
            manifest["pages"][slug] = imgs
            total += len(imgs)
            seen_global.update(i["src"] for i in imgs)
    manifest["base"] = origin or ""

    os.makedirs("orchestration/images", exist_ok=True)
    outp = f"orchestration/images/{project}.json"
    json.dump(manifest, open(outp, "w"), indent=2, ensure_ascii=False)
    print(f"extract_media: {len(pages)} page(s), {total} image refs "
          f"({len(seen_global)} unique) -> {outp}")
    # short per-page summary
    for slug, imgs in list(manifest["pages"].items())[:12]:
        roles = {}
        for i in imgs:
            roles[i["role"]] = roles.get(i["role"], 0) + 1
        print(f"  {slug:28s} {len(imgs):3d}  {roles}")


if __name__ == "__main__":
    main()
