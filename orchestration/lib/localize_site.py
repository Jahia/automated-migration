#!/usr/bin/env python3
"""localize_site.py — build a TRULY-LOCAL, self-contained mirror of the crawl.

The crawler caches HTML + top-level assets, but the HTML still points at the live
site and CSS-referenced resources (fonts, @import, url() backgrounds) are never
followed. So any render still phones home to acquia.com. This step fixes that:

  1. discover every asset referenced by each cached page (link/script/img/srcset/
     source/poster + inline style url()), AND recurse into CSS (@import, url(),
     @font-face src) — the part the crawler misses;
  2. download whatever is missing (crawler-cache-first, then live with WAF backoff);
  3. rewrite ALL references (HTML + CSS) to local, hash-named, relative paths;
  4. emit <project>/workflow-output/local-mirror/<slug>.html (self-contained) +
     assets/<sha1>.<ext> + mirror.json (per-page counts, bytes, the external residue
     that could NOT be localised, and a localizable %).

Deterministic: sha1-named assets, sorted iteration → byte-stable across runs.
Verified offline by mirror_probe.mjs (renders with all external network blocked).

Usage:
  python3 orchestration/lib/localize_site.py <project> [--max-asset-size MB] [--force]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
CONNECT_TIMEOUT = 20
MAX_RETRIES = 4

KIND_EXT = {"css": ".css", "js": ".js", "font": ".woff2", "img": ".png"}
CSS_EXTS = {".css"}
# real web asset extensions — a URL-path match is only trusted as the file ext when
# it is one of these (so version fragments like ".v14" / ".3" fall back to KIND_EXT).
KNOWN_EXTS = {".css", ".js", ".mjs", ".json", ".woff2", ".woff", ".ttf", ".otf", ".eot",
              ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico",
              ".mp4", ".webm", ".m4s", ".ogg", ".mp3"}


def sha(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def ext_of(url, kind=""):
    path = urllib.parse.urlparse(url).path
    m = re.search(r"(\.[A-Za-z0-9]{1,5})$", path)
    if m and m.group(1).lower() in KNOWN_EXTS:
        return m.group(1).lower()
    if kind in KIND_EXT:
        return KIND_EXT[kind]
    return m.group(1).lower() if m else ""


def local_name(url, kind=""):
    return sha(url) + ext_of(url, kind)


def crawler_cache_candidates(proj, url):
    """On-disk paths the crawler MAY have used for this URL. The crawler appends
    '.html' to an extension-less last segment; we probe that + '.bin' + raw, under
    both _assets and _crawl, so we reuse whatever was already downloaded."""
    p = urllib.parse.urlparse(url)
    path = p.path or "/"
    if path == "/":
        rels = [f"{p.netloc}/index.html"]
    else:
        base = p.netloc + path
        last = path.rstrip("/").rsplit("/", 1)[-1]
        if path.endswith("/"):
            rels = [base + "index.html"]
        elif "." not in last:
            rels = [base + ".html", base + ".bin", base]
        else:
            rels = [base]
    out = []
    for rel in rels:
        rel = re.sub(r"[^A-Za-z0-9._/-]", "_", rel)
        for sub in ("_assets", "_crawl"):
            out.append(os.path.join(proj, ".reference", "cache", sub, rel))
    return out


def http_get(url, max_size):
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
                cl = resp.headers.get("Content-Length")
                if cl and max_size:
                    try:
                        if int(cl.split(",")[0].strip()) > max_size:
                            return None
                    except ValueError:
                        pass  # malformed header — rely on the post-read length check
                data = resp.read((max_size + 1) if max_size else None)
                if max_size and len(data) > max_size:
                    return None
                return data
        except Exception as e:
            code = getattr(e, "code", None)
            if code in (403, 429, 500, 502, 503, 520, 521, 522, 523, 524):
                time.sleep(min(2 * (2 ** attempt), 30))
            else:
                return None
    return None


class Localizer:
    def __init__(self, proj, max_size, force):
        self.proj = proj
        self.max_size = max_size
        self.force = force
        # under workflow-output so the cockpit artifact endpoint can serve it
        self.mirror = os.path.join(proj, "workflow-output", "local-mirror")
        self.assets_dir = os.path.join(self.mirror, "assets")
        os.makedirs(self.assets_dir, exist_ok=True)
        self.reg = {}          # abs_url -> {"name","ok","bytes","kind"}
        self.residue = []      # abs_urls that could not be localised

    # ── asset acquisition ──────────────────────────────────────────
    def _read_bytes(self, url):
        """crawler-cache-first, then live (WAF-aware). Returns bytes or None."""
        if not self.force:
            for cp in crawler_cache_candidates(self.proj, url):
                if os.path.isfile(cp) and os.path.getsize(cp) > 0:
                    with open(cp, "rb") as f:
                        return f.read()
        return http_get(url, self.max_size)

    def register(self, abs_url, kind=""):
        """Ensure the asset is downloaded + written to the mirror. Returns its local
        name (for rewriting) or None if it could not be localised."""
        if not abs_url or abs_url.startswith("data:") or abs_url.startswith("blob:"):
            return None
        if abs_url in self.reg:
            return self.reg[abs_url]["name"] if self.reg[abs_url]["ok"] else None
        name = local_name(abs_url, kind)
        dest = os.path.join(self.assets_dir, name)
        is_css = ext_of(abs_url, kind) in CSS_EXTS or kind == "css"
        if os.path.isfile(dest) and not self.force and not is_css:
            self.reg[abs_url] = {"name": name, "ok": True, "bytes": os.path.getsize(dest), "kind": kind}
            return name
        data = self._read_bytes(abs_url)
        if data is None:
            self.reg[abs_url] = {"name": name, "ok": False, "bytes": 0, "kind": kind}
            self.residue.append(abs_url)
            return None
        if is_css:
            data = self._rewrite_css(data, abs_url)   # sibling refs (in assets/) → bare names
        with open(dest, "wb") as f:
            f.write(data)
        self.reg[abs_url] = {"name": name, "ok": True, "bytes": len(data), "kind": kind or ("css" if is_css else "")}
        return name

    # ── CSS: recurse + rewrite url()/@import/@font-face ─────────────
    # match the FULL url(...) or bare-string import (ref in group 2 or 4); do NOT
    # consume trailing media queries / the ')' is consumed only inside url(...).
    _CSS_IMPORT = re.compile(r"""@import\s+(?:url\(\s*(['"]?)([^'")]+)\1\s*\)|(['"])([^'"]+)\3)""", re.I)
    _CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.I)

    def _rewrite_css(self, data, css_url, prefix=""):
        """Rewrite url()/@import to local paths. `prefix` = '' when the CSS itself
        lives in assets/ (refs are siblings), 'assets/' when the CSS is inlined into
        a page at the mirror root."""
        try:
            text = data.decode("utf-8", "replace") if isinstance(data, (bytes, bytearray)) else data
        except Exception:
            return data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")

        def imp(m):
            ref = (m.group(2) or m.group(4) or "").strip()
            if not ref or ref.startswith("data:"):
                return m.group(0)
            absu = urllib.parse.urljoin(css_url, ref)
            nm = self.register(absu, "css")
            return f'@import "{(prefix + nm) if nm else absu}"'

        def url(m):
            ref = m.group(2).strip()
            if ref.startswith("data:") or ref.startswith("#"):
                return m.group(0)
            absu = urllib.parse.urljoin(css_url, ref)
            kind = "font" if re.search(r"\.(woff2?|ttf|otf|eot)(\?|$)", absu, re.I) else "img"
            nm = self.register(absu, kind)
            return f"url({(prefix + nm) if nm else absu})"

        text = self._CSS_IMPORT.sub(imp, text)
        text = self._CSS_URL.sub(url, text)
        return text.encode("utf-8")

    # ── HTML: rewrite every asset reference to the local mirror ─────
    def _srcset(self, value, base):
        out = []
        for part in re.split(r",\s+", value.strip()):
            seg = part.strip()
            if not seg:
                continue
            bits = seg.split()
            absu = urllib.parse.urljoin(base, bits[0])
            if absu.startswith("data:"):
                out.append(seg)
                continue
            nm = self.register(absu, "img")
            bits[0] = ("assets/" + nm) if nm else absu
            out.append(" ".join(bits))
        return ", ".join(out)

    _AS_KIND = {"style": "css", "script": "js", "font": "font", "image": "img"}

    def localise_page(self, slug, page_url, html):
        soup = BeautifulSoup(html, "lxml")
        for b in soup.find_all("base"):
            b.decompose()

        def relink(ref, kind):
            if not ref:
                return None
            absu = urllib.parse.urljoin(page_url, ref)
            nm = self.register(absu, kind)
            return ("assets/" + nm) if nm else absu   # residue → absolute live URL (degrades + is blocked offline)

        for link in soup.find_all("link"):
            rel = " ".join(link.get("rel", [])).lower()
            if not link.get("href") or not any(k in rel for k in ("stylesheet", "icon", "preload", "prefetch", "apple-touch")):
                continue
            kind = "css" if "stylesheet" in rel else self._AS_KIND.get((link.get("as") or "").lower(), "img")
            new = relink(link["href"], kind)
            if new:
                link["href"] = new
                link.attrs.pop("integrity", None)
                link.attrs.pop("crossorigin", None)
        # Handle imagesrcset on link tags (Next.js preload pattern)
        for link in soup.find_all("link", imagesrcset=True):
            link["imagesrcset"] = self._srcset(link["imagesrcset"], page_url)
        for scr in soup.find_all("script"):
            if scr.get("src"):
                new = relink(scr["src"], "js")
                if new:
                    scr["src"] = new
                    scr.attrs.pop("integrity", None)
                    scr.attrs.pop("crossorigin", None)
        # lazy-load attributes: the crawl captures PRE-hydration HTML where the
        # real URL lives ONLY in a data-* attr (src empty/absent); the site's JS
        # copies it to src on scroll — JS that runs neither in the offline mirror
        # NOR in the JS-stripped Jahia render. So we localise the data-* URL AND
        # MATERIALISE it into src/srcset, making the image load without any JS
        # (observed live: discoverasr 44 DAM images + contentful cards invisible).
        LAZY_SRC = ("data-src", "data-lazy-src", "data-original", "data-url")
        LAZY_SET = ("data-srcset", "data-lazy-srcset")
        for tag in soup.find_all(["img", "source", "video", "audio"]):
            lazy_src = next((tag.get(a) for a in LAZY_SRC if tag.get(a)), None)
            lazy_set = next((tag.get(a) for a in LAZY_SET if tag.get(a)), None)
            if tag.get("src"):
                new = relink(tag["src"], "img")
                if new:
                    tag["src"] = new
            elif lazy_src:                       # no src — materialise from data-*
                new = relink(lazy_src, "img")
                if new:
                    tag["src"] = new
            for a in LAZY_SRC:                   # localise the data-* attr in place too
                if tag.get(a):
                    nm = relink(tag[a], "img")
                    if nm:
                        tag[a] = nm
            if tag.get("poster"):
                new = relink(tag["poster"], "img")
                if new:
                    tag["poster"] = new
            if tag.get("srcset"):
                tag["srcset"] = self._srcset(tag["srcset"], page_url)
            elif lazy_set:                       # materialise srcset from data-srcset
                tag["srcset"] = self._srcset(lazy_set, page_url)
            for a in LAZY_SET:
                if tag.get(a):
                    tag[a] = self._srcset(tag[a], page_url)
        # inline style="… url() …" and <style> blocks live at the page root → prefix assets/
        for tag in soup.find_all(style=True):
            tag["style"] = self._rewrite_css(tag["style"], page_url, prefix="assets/").decode("utf-8", "replace")
        for st in soup.find_all("style"):
            if st.string:
                st.string = self._rewrite_css(st.string, page_url, prefix="assets/").decode("utf-8", "replace")

        # charset FIRST in <head>: rewritten <link> tags can push an existing meta
        # past the browser's 1024-byte sniff window → Latin-1 fallback → mojibake.
        head = soup.find("head")
        if head is not None:
            for m in head.find_all("meta", charset=True):
                m.decompose()
            meta = soup.new_tag("meta", charset="utf-8")
            head.insert(0, meta)

        out = os.path.join(self.mirror, f"{slug}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(str(soup))
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--max-asset-size", type=float, default=15, help="skip assets larger than N MB (default 15; 0 = unlimited)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    proj = args.project

    inv_path = f"{proj}/workflow-output/page-inventory.json"
    if not os.path.isfile(inv_path):
        print(f"FAIL: {inv_path} not found (run crawl first)", file=sys.stderr)
        sys.exit(1)
    inv = json.load(open(inv_path))
    pages = inv.get("pages", [])

    loc = Localizer(proj, int(args.max_asset_size * 1024 * 1024), args.force)
    page_recs = []
    for page in pages:
        html_path = os.path.join(proj, page.get("cachedAt", ""))
        if not os.path.isfile(html_path):
            continue
        try:
            html = open(html_path, errors="replace").read()
            before = len(loc.reg)
            out = loc.localise_page(page["slug"], page["url"], html)
            page_recs.append({"slug": page["slug"], "url": page["url"],
                              "htmlFile": os.path.relpath(out, loc.mirror),
                              "newAssets": len(loc.reg) - before})
        except Exception as e:  # one bad page must not abort the whole mirror
            page_recs.append({"slug": page["slug"], "url": page["url"], "error": str(e)[:200]})
            print(f"  WARNING: failed to localise {page['slug']}: {e}", file=sys.stderr)

    ok_assets = [a for a in loc.reg.values() if a["ok"]]
    total_bytes = sum(a["bytes"] for a in ok_assets)
    localizable = round(100 * len(ok_assets) / max(1, len(loc.reg)), 1)
    mirror = {
        "project": proj,
        "pages": page_recs,
        "assets": {"total": len(loc.reg), "localized": len(ok_assets),
                   "bytes": total_bytes, "localizablePct": localizable},
        "residue": sorted(set(loc.residue)),
    }
    with open(os.path.join(loc.mirror, "mirror.json"), "w") as f:
        json.dump(mirror, f, indent=2, ensure_ascii=False)

    print("=== LOCALIZE (self-contained local mirror) ===")
    print(f"pages: {len([p for p in page_recs if 'error' not in p])}/{len(page_recs)} | "
          f"assets: {len(ok_assets)}/{len(loc.reg)} localized ({localizable}%) | {total_bytes/1024/1024:.1f} MB")
    if loc.residue:
        print(f"external residue ({len(set(loc.residue))} not localizable):")
        for u in sorted(set(loc.residue))[:15]:
            print(f"  - {u}")
    print(f"Output: {loc.mirror}/  (<slug>.html + assets/ + mirror.json)")


if __name__ == "__main__":
    main()
