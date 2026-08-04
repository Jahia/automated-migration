#!/usr/bin/env python3
"""crawl-site.py — Cached, rate-limited site crawler with asset download.

Downloads HTML pages AND their referenced assets (CSS, JS, images) locally.
Supports --max-pages for fast iteration on a subset of pages.

Usage:
  python3 orchestration/lib/crawl-site.py <project> <url> [options]

Options:
  --max-pages N    Stop after N pages (0 = unlimited)
  --depth D        Max crawl depth (default 3)
  --lang LANG      Only crawl pages matching this language prefix (e.g. fr-FR)
  --force          Re-download even if cached
  --max-asset-size MB  Skip assets larger than MB (default 5)

Outputs:
  <project>/.reference/cache/_crawl/     — HTML pages
  <project>/.reference/cache/_assets/    — CSS, JS, images
  <project>/workflow-output/page-inventory.json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance  # noqa: E402  (stamps page-inventory.json)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
RATE_DELAY = 2.0
MAX_RETRIES = 3
CONNECT_TIMEOUT = 15
MAX_ASSET_SIZE = 5 * 1024 * 1024  # 5 MB

# P4: bump when the crawl/render/download algorithm changes (e.g. render_page.mjs
# capture logic, retry/backoff policy) — invalidates the WHOLE on-disk cache for a
# project (a stale cache is silently wrong: same path, algorithm-different bytes).
# The version lives in one marker file per project (not per cached page — thousands
# of sidecar files would be wasteful), so a bump forces a full honest re-crawl once;
# is_cached() reads it fresh each call and never raises on an absent/old marker.
TOOL_VERSION = 1

# An origin that answers 500/404 with a rendered error PAGE (status 200 or not)
# must not have that page cached as content: measured on salonphoto, 8 declared
# entity URLs answered "500 — Internal server error" and were cached as pages, so
# they would have loaded as titleless empty nodes. Detected on the RENDERED result
# (a thin <main> with no headings under an error title), because a 4xx/5xx body
# served with a 200 status defeats any status-code check.
ERROR_TITLE = re.compile(r"(?:^|\W)(4\d\d|5\d\d)\s*[—–-]\s*|internal server error|"
                         r"page not found|something went wrong|page introuvable|"
                         r"erreur interne", re.I)


def is_error_page(html):
    mt = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S | re.I)
    title = re.sub(r"\s+", " ", mt.group(1) if mt else "").strip()
    if not ERROR_TITLE.search(title):
        return None
    mm = re.search(r"<main[^>]*>(.*?)</main>", html or "", re.S | re.I)
    region = mm.group(1) if mm else ""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", region)).strip()
    # no <main> at all under an error title is itself the signal (the rendered 500
    # ships chrome only), so do not fall back to measuring the whole document
    if (mm is None or len(text) < 600) and not re.search(r"<h[12]\b", region or (html or ""), re.I):
        return title[:60]
    return None


ASSET_EXTS = {'.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif',
              '.woff', '.woff2', '.ttf', '.eot', '.ico', '.pdf'}

# Pages that are not content (utility, legal, search, etc.)
UTILITY_PATTERNS = [
    r'/recherche', r'/search', r'/plan-du-site', r'/sitemap',
    r'/cookies', r'/mentions-legales', r'/legal', r'/privacy',
    r'/protection-donnees', r'/rgpd', r'/billet', r'/newsletter',
    r'/inscription', r'/login', r'/connexion', r'/register',
    r'/404', r'/erreur', r'/error', r'/thank-you', r'/merci',
    r'/ajax', r'/api/', r'/modules/', r'/graphql',
]


class AssetExtractor(HTMLParser):
    """Extract asset URLs from HTML."""

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.assets = set()

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == 'link':
            href = attrs_d.get('href', '')
            rel = attrs_d.get('rel', '')
            if href and ('stylesheet' in rel or 'icon' in rel or 'preload' in rel):
                self.assets.add(self._resolve(href))
        elif tag == 'script':
            src = attrs_d.get('src', '')
            if src:
                self.assets.add(self._resolve(src))
        elif tag == 'img':
            src = attrs_d.get('src', '')
            srcset = attrs_d.get('srcset', '')
            if src and not src.startswith('data:'):
                self.assets.add(self._resolve(src))
            if srcset:
                for part in srcset.split(','):
                    url = part.strip().split()[0] if part.strip() else ''
                    if url and not url.startswith('data:'):
                        self.assets.add(self._resolve(url))
        elif tag == 'source':
            srcset = attrs_d.get('srcset', '')
            if srcset:
                for part in srcset.split(','):
                    url = part.strip().split()[0] if part.strip() else ''
                    if url and not url.startswith('data:'):
                        self.assets.add(self._resolve(url))
        elif tag == 'meta':
            prop = attrs_d.get('property', '') or attrs_d.get('name', '')
            content = attrs_d.get('content', '')
            if 'image' in prop and content:
                self.assets.add(self._resolve(content))

    def _resolve(self, url):
        return urllib.parse.urljoin(self.base_url, url)


class LinkExtractor(HTMLParser):
    """Extract internal links from HTML for crawling."""

    def __init__(self, base_url, origin):
        super().__init__()
        self.base_url = base_url
        self.origin = origin
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag in ('a', 'area'):
            href = dict(attrs).get('href', '')
            if href:
                resolved = urllib.parse.urljoin(self.base_url, href)
                parsed = urllib.parse.urlparse(resolved)
                if parsed.netloc == self.origin and parsed.scheme in ('http', 'https'):
                    clean = urllib.parse.urlunparse(parsed._replace(fragment=''))
                    if not self._is_asset(clean):
                        self.links.add(clean)

    def _is_asset(self, url):
        path = urllib.parse.urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in ASSET_EXTS)


def normalize_url(url):
    """Normalize URL for deduplication."""
    parsed = urllib.parse.urlparse(url)
    # Remove trailing slash from path
    path = parsed.path.rstrip('/') or '/'
    # Remove default ports
    netloc = parsed.netloc
    if netloc.endswith(':80') and parsed.scheme == 'http':
        netloc = netloc[:-3]
    elif netloc.endswith(':443') and parsed.scheme == 'https':
        netloc = netloc[:-4]
    # Reconstruct without fragment
    return urllib.parse.urlunparse((parsed.scheme, netloc, path, parsed.params, parsed.query, ''))


def is_utility_page(url):
    """Check if a URL matches a utility page pattern."""
    path = urllib.parse.urlparse(url).path.lower()
    return any(re.search(pattern, path) for pattern in UTILITY_PATTERNS)


def matches_language(url, lang):
    """Check if a URL matches the target language."""
    if not lang:
        return True
    path = urllib.parse.urlparse(url).path
    # Match /fr-FR, /fr, /fr/ etc.
    return path.startswith(f'/{lang}') or path == f'/{lang}'


def cache_path(proj, url, subdir='_crawl'):
    """Deterministic on-disk path for a URL.

    Decides file-vs-index from the URL PATH's last segment, not the whole key —
    otherwise a bare host like www.example.com (dots in the host) is saved as a
    FILE and any child page then collides trying to create a dir of that name.
    """
    p = urllib.parse.urlparse(url)
    path = p.path
    if not path or path == '/':
        rel = f"{p.netloc}/index.html"
    else:
        last = path.rstrip('/').rsplit('/', 1)[-1]
        rel = p.netloc + path
        if path.endswith('/'):
            rel += 'index.html'
        elif '.' not in last:
            rel += '.html'
    rel = re.sub(r'[^A-Za-z0-9._/-]', '_', rel)
    return os.path.join(proj, '.reference', 'cache', subdir, rel)


def _cache_version_marker(proj):
    return os.path.join(proj, '.reference', 'cache', '.tool-version')


def cache_version_ok(proj):
    """False when the on-disk cache predates TOOL_VERSION (or has no marker yet)
    — every is_cached() lookup then reads as a MISS so a bumped algorithm gets an
    honest re-download/re-render instead of trusting stale bytes. Never raises."""
    try:
        with open(_cache_version_marker(proj)) as f:
            return f.read().strip() == str(TOOL_VERSION)
    except OSError:
        return False


def stamp_cache_version(proj):
    """Refresh the marker once the cache is known-consistent with TOOL_VERSION
    (called at the end of a completed crawl — never mid-run, or a fresh miss on
    page 1 would get 'healed' into a false hit on page 2)."""
    try:
        with open(_cache_version_marker(proj), 'w') as f:
            f.write(str(TOOL_VERSION))
    except OSError:
        pass


def is_cached(path, proj=None):
    if proj is not None and not cache_version_ok(proj):
        return False
    return os.path.isfile(path) and os.path.getsize(path) > 0


def download(url, dest, rate_delay=RATE_DELAY, max_size=0):
    """Download a URL with rate limiting and retry. Returns (success, bytes_downloaded)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            })
            with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
                # Check content-length before downloading
                content_length = resp.headers.get('Content-Length')
                if content_length and max_size and int(content_length) > max_size:
                    print(f"  SKIP (too large: {int(content_length)/1024/1024:.1f} MB): {url}", file=sys.stderr)
                    return False, 0
                data = resp.read(max_size + 1 if max_size else None)
                if max_size and len(data) > max_size:
                    print(f"  SKIP (too large: {len(data)/1024/1024:.1f} MB): {url}", file=sys.stderr)
                    return False, 0
                with open(dest, 'wb') as f:
                    f.write(data)
                return True, len(data)
        except Exception as e:
            code = getattr(e, 'code', None)
            if code in (403, 429, 500, 502, 503, 520, 521, 522, 523, 524):
                backoff = min(rate_delay * (2 ** attempt), 120)
                print(f"  WAF/rate-limit (HTTP {code}) — backoff {backoff:.0f}s", file=sys.stderr)
                time.sleep(backoff)
                rate_delay *= 1.5
            else:
                return False, 0
    return False, 0


def render_html(url, dest, timeout=60):
    """Capture the POST-HYDRATION DOM via render_page.mjs (Playwright). The raw
    HTTP response is the empty shell of any client-rendered site; this is what a
    visitor actually sees. UNIFORM — every HTML page is rendered, no SPA branch
    (a server-rendered page's post-JS DOM ≈ its HTML). Returns (ok, bytes)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        r = subprocess.run(["node", os.path.join(here, "render_page.mjs"), url, dest],
                           capture_output=True, text=True, timeout=timeout,
                           cwd=os.path.dirname(os.path.dirname(here)))
        if r.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return True, os.path.getsize(dest)
        if r.stderr:
            print(f"  render fallback ({r.stderr.strip().splitlines()[-1][:80] if r.stderr.strip() else 'no output'})", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"  render timeout → urllib fallback: {url}", file=sys.stderr)
    except Exception as e:
        print(f"  render error → urllib fallback: {str(e)[:80]}", file=sys.stderr)
    return False, 0


def extract_assets(html_path, base_url):
    """Extract asset URLs from an HTML file."""
    try:
        with open(html_path, 'r', errors='replace') as f:
            html = f.read()
    except Exception:
        return set()
    parser = AssetExtractor(base_url)
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.assets


def extract_links(html_path, base_url, origin):
    """Extract internal links from an HTML file."""
    try:
        with open(html_path, 'r', errors='replace') as f:
            html = f.read()
    except Exception:
        return set()
    parser = LinkExtractor(base_url, origin)
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.links


def slug_from_url(url, origin, lang=None):
    """Extract a human-readable slug from a URL."""
    path = urllib.parse.urlparse(url).path
    path = re.sub(r'^/', '', path)
    # Remove language prefix
    if lang and path.startswith(lang + '/'):
        path = path[len(lang) + 1:]
    elif lang and path == lang:
        path = ''
    path = re.sub(r'\.(html|htm|php|aspx?)$', '', path)
    path = path.rstrip('/')
    if not path:
        return 'home'
    return path.replace('/', '_')


def main():
    parser = argparse.ArgumentParser(description='Cached site crawler with asset download')
    parser.add_argument('project', help='Project path (e.g. projects/supercar-garage)')
    parser.add_argument('url', help='Start URL to crawl')
    parser.add_argument('--max-pages', type=int, default=0, help='Max pages to crawl (0 = unlimited)')
    parser.add_argument('--depth', type=int, default=3, help='Max crawl depth (default 3)')
    parser.add_argument('--lang', default='', help='Only crawl pages matching this language prefix (e.g. fr-FR)')
    parser.add_argument('--force', action='store_true', help='Re-download even if cached')
    parser.add_argument('--max-asset-size', type=float, default=5, help='Skip assets larger than N MB (default 5)')
    parser.add_argument('--rate-delay', type=float, default=RATE_DELAY, help='Base delay between requests')
    parser.add_argument('--no-render', action='store_true',
                        help='disable browser rendering (raw HTTP only) — server-rendered sites '
                             'only; client-rendered pages will capture the empty shell')
    parser.add_argument('--url-list',
                        help='file of URL paths (one per line, # comments) — crawl EXACTLY '
                             'these, no link following (nav-driven scope, 2026-07-20 '
                             'three-section pilot)')
    parser.add_argument('--merge-inventory', action='store_true',
                        help='merge crawled pages into the existing page-inventory.json '
                             'instead of rewriting it (incremental section crawl)')
    args = parser.parse_args()

    proj = args.project
    start_url = args.url.rstrip('/')
    origin = urllib.parse.urlparse(start_url).netloc
    depth = args.depth
    max_pages = args.max_pages
    lang = args.lang
    rate_delay = args.rate_delay
    max_asset_bytes = int(args.max_asset_size * 1024 * 1024)

    os.makedirs(os.path.join(proj, '.reference', 'cache', '_crawl'), exist_ok=True)
    os.makedirs(os.path.join(proj, '.reference', 'cache', '_assets'), exist_ok=True)
    os.makedirs(os.path.join(proj, 'workflow-output'), exist_ok=True)

    # Crawl queue: (url, current_depth)
    queue = [(start_url, 0)]
    if args.url_list:
        base = f"https://{origin}"
        queue = []
        for line in open(args.url_list):
            l = line.strip()
            if not l or l.startswith('#'):
                continue
            queue.append((base + l if l.startswith('/') else l, depth))
        # depth == current_depth on every seed: no link following — the list
        # IS the scope (nav-driven, bounded by the source's own menus)
    visited = set()  # Normalized URLs
    pages = []
    failed = []
    skipped_utility = []
    skipped_lang = []
    assets_downloaded = 0
    assets_bytes = 0
    crawl_start = time.time()

    print(f"Crawling {start_url}")
    print(f"  max-pages={max_pages or 'unlimited'}, depth={depth}, lang={lang or 'all'}")

    while queue:
        if max_pages and len(pages) >= max_pages:
            print(f"Reached max-pages limit ({max_pages})")
            break

        url, current_depth = queue.pop(0)

        # Normalize and deduplicate
        normalized = normalize_url(url)
        if normalized in visited:
            continue
        visited.add(normalized)

        # Skip utility pages
        if is_utility_page(url):
            skipped_utility.append(url)
            continue

        # Skip wrong language (except the start URL which we always accept)
        if lang and not matches_language(url, lang) and url != start_url:
            skipped_lang.append(url)
            continue

        # Download page
        page_cache = cache_path(proj, url, '_crawl')
        if not args.force and is_cached(page_cache, proj):
            print(f"  [cached] {url}")
        else:
            print(f"  [{len(pages)+1}] {url}")
            time.sleep(rate_delay)
            # render the post-hydration DOM (uniform; captures client-rendered
            # content), fall back to raw HTTP if the render fails
            ok = False
            if not args.no_render:
                ok, nbytes = render_html(url, page_cache)
                if ok:
                    print(f"      rendered {nbytes//1024} KB (post-hydration DOM)")
            if not ok:
                ok, _ = download(url, page_cache, rate_delay)
            if not ok:
                failed.append({'url': url, 'error': 'download failed'})
                continue

        # Extract slug and title
        slug = slug_from_url(url, origin, lang)
        title = ''
        try:
            with open(page_cache, 'r', errors='replace') as f:
                html = f.read()
            m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
            if m:
                title = re.sub(r'\s+', ' ', m.group(1)).strip()
        except Exception:
            pass

        pages.append({
            'url': url,
            'slug': slug,
            'title': title,
            'httpStatus': 200,
            'cachedAt': os.path.relpath(page_cache, proj),
            'contentLength': os.path.getsize(page_cache),
        })

        # Extract and download assets
        assets = extract_assets(page_cache, url)
        for asset_url in assets:
            asset_path = cache_path(proj, asset_url, '_assets')
            if not args.force and is_cached(asset_path, proj):
                continue
            ok, nbytes = download(asset_url, asset_path, rate_delay, max_asset_bytes)
            if ok:
                assets_downloaded += 1
                assets_bytes += nbytes

        # Rewrite HTML to use local assets
        # (skip for now — causes issues with relative paths in nested dirs)

        # Extract internal links for next depth level
        if current_depth < depth:
            links = extract_links(page_cache, url, origin)
            for link in sorted(links):
                norm = normalize_url(link)
                if norm not in visited:
                    queue.append((link, current_depth + 1))

    # Write page-inventory.json
    inv_prev_path = os.path.join(proj, 'workflow-output', 'page-inventory.json')
    if args.merge_inventory and os.path.exists(inv_prev_path):
        # incremental section crawl (2026-07-20): keep every previously
        # crawled page, overwrite same-slug entries with the fresh capture
        prev = json.load(open(inv_prev_path))
        new_slugs = {p['slug'] for p in pages}
        pages = [p for p in (prev.get('pages') or [])
                 if p.get('slug') not in new_slugs] + pages
        start_url = prev.get('siteUrl') or start_url
    # capture variants are never page identities (2026-07-23: .recon slugs —
    # chrome re-captures of existing pages — leaked into the inventory via a
    # mirror-derived url-list and downstream tried to create duplicate pages)
    pages = [p for p in pages if not (p.get('slug') or '').endswith('.recon')]
    inventory = {
        'siteUrl': start_url,
        'crawledAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'pages': pages,
        'totalPages': len(pages),
        'failedPages': failed,
        'assetsDownloaded': assets_downloaded,
        'assetsBytes': assets_bytes,
        'maxPages': max_pages or 'unlimited',
        'depth': depth,
        'lang': lang or 'all',
        'skippedUtility': len(skipped_utility),
        'skippedLang': len(skipped_lang),
    }
    provenance.stamp_json(inventory, 'crawl-site.py',
                          page_set=[p['slug'] for p in pages])
    inv_path = os.path.join(proj, 'workflow-output', 'page-inventory.json')
    with open(inv_path, 'w') as f:
        json.dump(inventory, f, indent=2)
    stamp_cache_version(proj)  # cache is now fully consistent with TOOL_VERSION

    duration = time.time() - crawl_start
    print(f"\n{'='*50}")
    print(f"CRAWL COMPLETE")
    print(f"  Pages:      {len(pages)}")
    print(f"  Assets:     {assets_downloaded} ({assets_bytes/1024/1024:.1f} MB)")
    print(f"  Failed:     {len(failed)}")
    print(f"  Skipped:    {len(skipped_utility)} utility, {len(skipped_lang)} wrong lang")
    print(f"  Duration:   {duration:.0f}s")
    print(f"  Output:     {inv_path}")
    if failed:
        print(f"\nFailed pages:")
        for f_item in failed[:10]:
            print(f"    - {f_item['url']} ({f_item['error']})")


if __name__ == '__main__':
    main()
