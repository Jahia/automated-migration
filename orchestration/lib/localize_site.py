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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance  # noqa: E402  (stamps local-mirror/mirror.json)

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


def normalize_url(url):
    """Canonicalise an asset URL to the percent-encoded form a browser SENDS and
    the crawler CACHED.

    The rendered-DOM crawl (render_page.mjs → document.outerHTML) serializes URLs
    with characters DECODED — a source `Brand%20logo.svg` comes back as
    `Brand logo.svg` (literal space), and AEM `.transform/<rendition>` paths carry
    spaces/parens verbatim. But (a) urllib puts a raw space straight into the HTTP
    request line → the origin 400s, and (b) crawl-site.py cached the asset under
    its ENCODED path (`%20` → sanitized `_20`), so a literal-space probe misses.
    Percent-encoding the path (and query) with `quote(safe="/%")` is idempotent
    (an already-encoded `%20` is preserved, a raw space becomes `%20`), so both
    occurrence forms collapse to ONE canonical URL — the download works and the
    cache probe matches. Fragments are dropped (never sent to the server)."""
    if not url or url.startswith(("data:", "blob:")):
        return url
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return url
    if not p.scheme and not p.netloc and not p.path:
        return url
    path = urllib.parse.quote(p.path, safe="/%:@&=+$,;~()!*'")
    query = urllib.parse.quote(p.query, safe="/%:@&=+$,;~()!*'?") if p.query else ""
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, query, ""))


def ext_of(url, kind=""):
    path = urllib.parse.urlparse(url).path
    m = re.search(r"(\.[A-Za-z0-9]{1,5})$", path)
    if m and m.group(1).lower() in KNOWN_EXTS:
        return m.group(1).lower()
    if kind in KIND_EXT:
        return KIND_EXT[kind]
    return m.group(1).lower() if m else ""


def local_name(url, kind=""):
    # hash the NORMALIZED form so the same asset written raw-with-spaces,
    # protocol-relative, or percent-encoded all collapse to ONE local file.
    return sha(normalize_url(url)) + ext_of(normalize_url(url), kind)


def _cache_rels(netloc, path):
    """The relative cache keys crawl-site.py would derive from a (netloc, path):
    it appends '.html' to an extension-less last segment, 'index.html' to a
    trailing '/', else uses the path as-is."""
    if path == "/" or not path:
        return [f"{netloc}/index.html"]
    base = netloc + path
    last = path.rstrip("/").rsplit("/", 1)[-1]
    if path.endswith("/"):
        return [base + "index.html"]
    if "." not in last:
        return [base + ".html", base + ".bin", base]
    return [base]


def crawler_cache_candidates(proj, url):
    """On-disk paths the crawler MAY have used for this URL. crawl-site.py stores
    an asset under `re.sub(r'[^A-Za-z0-9._/-]', '_', netloc+path)` of the URL AS
    RESOLVED FROM RAW HTML — where a space is still `%20` (→ sanitized `_20`).
    The rendered-DOM localize step sees the SAME asset with the space DECODED, so
    we must probe BOTH the percent-encoded path (matches the crawler's `_20`) and
    the raw/decoded path — under both _assets and _crawl."""
    p = urllib.parse.urlparse(url)
    raw_path = p.path or "/"
    enc_path = urllib.parse.urlsplit(normalize_url(url)).path or "/"
    rels = []
    for path in dict.fromkeys((enc_path, raw_path)):   # encoded first, dedup, order-stable
        rels.extend(_cache_rels(p.netloc, path))
    out = []
    seen = set()
    for rel in rels:
        rel = re.sub(r"[^A-Za-z0-9._/-]", "_", rel)
        for sub in ("_assets", "_crawl"):
            cp = os.path.join(proj, ".reference", "cache", sub, rel)
            if cp not in seen:
                seen.add(cp)
                out.append(cp)
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
        self.reg = {}          # abs_url (raw, as seen in markup) -> {"name","ok","bytes","kind"}
        self.residue = []      # abs_urls that could not be localised
        self.urlmap = {}       # every URL FORM of a localised asset -> local name (rule 31)

    # ── asset acquisition ──────────────────────────────────────────
    def _read_bytes(self, url):
        """crawler-cache-first, then live (WAF-aware). Returns bytes or None. The
        probe uses `url` verbatim (crawler_cache_candidates covers raw+encoded);
        the live fetch is always over the NORMALIZED URL (a raw space in the
        request line is a hard 400)."""
        if not self.force:
            for cp in crawler_cache_candidates(self.proj, url):
                if os.path.isfile(cp) and os.path.getsize(cp) > 0:
                    with open(cp, "rb") as f:
                        return f.read()
        return http_get(normalize_url(url), self.max_size)

    def _record_forms(self, abs_url, name):
        """Register EVERY URL form of a localised asset → its local name, so a
        downstream rewrite matches whatever the captured markup actually uses
        (rule 31): raw, percent-encoded, protocol-relative, and root-relative."""
        forms = {abs_url, normalize_url(abs_url)}
        for u in list(forms):
            try:
                p = urllib.parse.urlsplit(u)
            except Exception:
                continue
            if p.scheme in ("http", "https") and p.netloc:
                forms.add("//" + p.netloc + p.path + (("?" + p.query) if p.query else ""))
                forms.add(p.path + (("?" + p.query) if p.query else ""))
        for f in forms:
            if f:
                self.urlmap.setdefault(f, name)

    def register(self, abs_url, kind=""):
        """Ensure the asset is downloaded + written to the mirror. Returns its local
        name (for rewriting) or None if it could not be localised. `reg` is keyed by
        the RAW url (the form that appears in the markup) so the residue ledger and
        idempotence match the occurrence; the hash/fetch canonicalise internally."""
        if not abs_url or abs_url.startswith("data:") or abs_url.startswith("blob:"):
            return None
        if abs_url in self.reg:
            return self.reg[abs_url]["name"] if self.reg[abs_url]["ok"] else None
        name = local_name(abs_url, kind)
        dest = os.path.join(self.assets_dir, name)
        is_css = ext_of(abs_url, kind) in CSS_EXTS or kind == "css"
        if os.path.isfile(dest) and not self.force and not is_css:
            self.reg[abs_url] = {"name": name, "ok": True, "bytes": os.path.getsize(dest), "kind": kind}
            self._record_forms(abs_url, name)
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
        self._record_forms(abs_url, name)
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
    _SRCSET_DESC = re.compile(r"^\d+(?:\.\d+)?[wx]$")

    def _srcset(self, value, base):
        out = []
        for part in re.split(r",\s+", value.strip()):
            seg = part.strip()
            if not seg:
                continue
            bits = seg.split()
            # srcset URLs may carry UNENCODED SPACES (malformed but browser-tolerated;
            # seen on AEM DAM paths: ".../SEO Article 2 Thumbnail.jpg 320w"). The
            # descriptor is the trailing NNNw/N.Nx token — everything before it is
            # the URL, spaces included; a naive bits[0] truncates at the first space.
            if len(bits) > 1 and self._SRCSET_DESC.match(bits[-1]):
                url_raw, desc = " ".join(bits[:-1]), [bits[-1]]
            else:
                url_raw, desc = " ".join(bits), []
            absu = urllib.parse.urljoin(base, url_raw.replace(" ", "%20"))
            if absu.startswith("data:"):
                out.append(seg)
                continue
            nm = self.register(absu, "img")
            out.append(" ".join([("assets/" + nm) if nm else absu] + desc))
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
            # dns-prefetch/preconnect hrefs are bare origins, not assets — and
            # "prefetch" as a substring test would match "dns-prefetch".
            if set(rel.split()) & {"dns-prefetch", "preconnect"}:
                continue
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
            # force EAGER decoding: a below-the-fold loading="lazy" image never
            # decodes inside the fidelity probe's render window (it does not
            # scroll), collapsing to a 0×0 box. Both the reference render AND
            # the Jahia render (skeletonRender.sanitizeFragment does the same
            # on the served side) must be deterministic here, not a timing race.
            if tag.name == "img" and tag.get("loading", "").lower() == "lazy":
                del tag["loading"]
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

    # INCREMENTAL (2026-08-04). Localizing is not cheap on a real corpus: 169 pages of
    # 85-240KB each, parsed and rewritten, on EVERY run — and this step re-runs on every
    # capture retry, every scope change and every restart. The assets were already on
    # disk (1027 files, unchanged) yet each run redid all the page rewriting.
    #
    # The registry is what made naive skipping unsafe: mirror.json's urlMap is built up
    # per page as pages are processed, so skipping a page used to drop its assets from
    # the map. But the urlMap is GLOBAL, so it can simply be seeded from the previous
    # mirror.json — then a page whose output is newer than its captured source is
    # already correct and can be skipped without losing a single mapping. --force still
    # rebuilds everything.
    prev_map, reused = {}, 0
    mj = os.path.join(loc.mirror, "mirror.json")
    if not args.force and os.path.isfile(mj):
        try:
            _prev = json.load(open(mj))
            for _u, _name in (_prev.get("urlMap") or {}).items():
                loc.reg.setdefault(_u, {"name": os.path.basename(_name), "ok": True,
                                        "bytes": 0, "kind": ""})
            prev_map = _prev.get("urlMap") or {}
        except (OSError, ValueError):
            prev_map = {}

    # NEVER WRITE A POORER REGISTRY THAN THE MIRROR ALREADY NEEDS (2026-08-04, self-
    # inflicted). Skipping pages is only safe if the urlMap carries forward: seeding it
    # from a mirror.json that a killed run had left without one produced 169 "reused"
    # pages and an EMPTY registry, while 1063 asset files and every page reference
    # stayed on disk — a mirror that looks complete and serves nothing. If pages
    # reference assets but the seed is empty, the incremental path is unsafe: rebuild.
    _refs = 0
    try:
        import glob as _g
        for _f in _g.glob(os.path.join(loc.mirror, "*.html"))[:5]:
            _refs += len(re.findall(r"assets/[0-9a-f]{8,}\.",
                                    open(_f, encoding="utf-8", errors="replace").read()))
    except Exception:                                              # noqa: BLE001
        _refs = 0
    if _refs and not prev_map:
        print("  ! incremental DISABLED: the mirror's pages reference assets but the "
              "previous mirror.json carries no urlMap — skipping pages would write an "
              "empty registry. Rebuilding in full.")
        prev_map = {}
        _incremental_ok = False
    else:
        _incremental_ok = True

    def _fresh(page):
        """the mirror output exists and is newer than the captured source"""
        if args.force or not _incremental_ok:
            return False
        src = os.path.join(proj, page.get("cachedAt", ""))
        out = os.path.join(loc.mirror, f"{page.get('slug')}.html")
        try:
            return (os.path.isfile(out) and os.path.isfile(src)
                    and os.path.getmtime(out) >= os.path.getmtime(src))
        except OSError:
            return False
    page_recs = []
    for page in pages:
        html_path = os.path.join(proj, page.get("cachedAt", ""))
        if not os.path.isfile(html_path):
            continue
        if _fresh(page):
            reused += 1
            page_recs.append({"slug": page["slug"], "url": page["url"],
                              "htmlFile": f"{page['slug']}.html", "newAssets": 0,
                              "reused": True})
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

    if reused:
        print(f"  ~ incremental: {reused} page(s) already current (mirror newer than "
              f"capture), {len(pages) - reused} rewritten; urlMap seeded with "
              f"{len(prev_map)} known asset(s) — --force to rebuild all")
    ok_assets = [a for a in loc.reg.values() if a["ok"]]
    total_bytes = sum(a["bytes"] for a in ok_assets)
    localizable = round(100 * len(ok_assets) / max(1, len(loc.reg)), 1)
    mirror = {
        "project": proj,
        "pages": page_recs,
        "assets": {"total": len(loc.reg), "localized": len(ok_assets),
                   "bytes": total_bytes, "localizablePct": localizable},
        # urlMap: every URL FORM of a localised asset -> its local mirror path
        # (relative to local-mirror/, i.e. "assets/<sha1>.<ext>"). Keyed by the
        # ORIGINAL forms as they appear in markup (raw-with-spaces, percent-
        # encoded, protocol-relative, root-relative) so a downstream resolver can
        # map an occurrence back to the localised file. (rule 31)
        "urlMap": {k: "assets/" + n for k, n in sorted(loc.urlmap.items())},
        "residue": sorted(set(loc.residue)),
    }
    provenance.stamp_json(mirror, "localize_site.py",
                          page_set=[p["slug"] for p in page_recs])
    with open(os.path.join(loc.mirror, "mirror.json"), "w") as f:
        json.dump(mirror, f, indent=2, ensure_ascii=False)

    # A completed (re-)localization makes any prior scope snapshot STALE:
    # scope_apply.py only snapshots local-mirror -> local-mirror-prescope when the
    # prescope dir is ABSENT, then rebuilds every page FROM it. Leaving an old
    # prescope means the next scope pass rebuilds from pre-relocalize bytes. Remove
    # it so scope_apply re-snapshots the fresh mirror and its byte-comparison
    # auto-invalidates the segmentation artifacts of every changed page (that
    # machinery lives in scope_apply and is tested there).
    prescope = os.path.join(proj, "workflow-output", "local-mirror-prescope")
    if os.path.isdir(prescope):
        import shutil
        shutil.rmtree(prescope, ignore_errors=True)
        print(f"removed stale scope snapshot: {prescope}")

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
