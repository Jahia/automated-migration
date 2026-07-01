#!/usr/bin/env python3
"""crawl-site.py — Cached, rate-limited site crawler with asset download.

Downloads HTML pages AND their referenced assets (CSS, JS, images) locally.
Supports --max-pages for fast iteration on a subset of pages.

Usage:
  python3 orchestration/lib/crawl-site.py <project> <url> [--max-pages N] [--depth D] [--force]

Outputs:
  <project>/.reference/cache/_crawl/     — HTML pages
  <project>/.reference/cache/_assets/    — CSS, JS, images
  <project>/workflow-output/page-inventory.json

Features:
  - Cache-first: never re-downloads what's already on disk
  - Rate-limited with WAF backoff
  - Downloads referenced assets (CSS, JS, images, fonts)
  - Rewrites HTML to use local asset paths
  - --max-pages N: stop after N pages (for testing)
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
from html.parser import HTMLParser
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
RATE_DELAY = 2.0
MAX_RETRIES = 3
CONNECT_TIMEOUT = 15
ASSET_EXTS = {'.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif',
              '.woff', '.woff2', '.ttf', '.eot', '.ico', '.pdf'}


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
            if src:
                self.assets.add(self._resolve(src))
            if srcset:
                for part in srcset.split(','):
                    url = part.strip().split()[0] if part.strip() else ''
                    if url:
                        self.assets.add(self._resolve(url))
        elif tag == 'source':
            srcset = attrs_d.get('srcset', '')
            if srcset:
                for part in srcset.split(','):
                    url = part.strip().split()[0] if part.strip() else ''
                    if url:
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
                    # Strip fragment and normalize
                    clean = urllib.parse.urlunparse(parsed._replace(fragment=''))
                    if not self._is_asset(clean):
                        self.links.add(clean)

    def _is_asset(self, url):
        path = urllib.parse.urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in ASSET_EXTS)


def cache_path(proj, url, subdir='_crawl'):
    """Deterministic on-disk path for a URL."""
    key = re.sub(r'^https?://', '', url)
    key = re.sub(r'\?.*$', '', key)
    key = re.sub(r'[^A-Za-z0-9._/-]', '_', key)
    if key.endswith('/'):
        key += 'index.html'
    if '.' not in os.path.basename(key):
        key += '.html'
    return os.path.join(proj, '.reference', 'cache', cache_subdir(url, subdir), key)


def cache_subdir(url, default='_crawl'):
    """Assets go to _assets, pages go to _crawl."""
    path = urllib.parse.urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in ASSET_EXTS):
        return '_assets'
    return default


def is_cached(path):
    return os.path.isfile(path) and os.path.getsize(path) > 0


def download(url, dest, rate_delay=RATE_DELAY):
    """Download a URL with rate limiting and retry."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            })
            with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
                data = resp.read()
                with open(dest, 'wb') as f:
                    f.write(data)
                return True
        except Exception as e:
            code = getattr(e, 'code', None)
            if code in (403, 429, 500, 502, 503, 520, 521, 522, 523, 524):
                backoff = min(rate_delay * (2 ** attempt), 120)
                print(f"  WAF/rate-limit (HTTP {code}) on {url} — backoff {backoff:.0f}s", file=sys.stderr)
                time.sleep(backoff)
                rate_delay *= 1.5
            else:
                print(f"  Error downloading {url}: {e}", file=sys.stderr)
                return False
    print(f"  BLOCKED after {MAX_RETRIES} attempts: {url}", file=sys.stderr)
    return False


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


def rewrite_assets(html_path, proj):
    """Rewrite HTML to reference local asset paths."""
    try:
        with open(html_path, 'r', errors='replace') as f:
            html = f.read()
    except Exception:
        return

    # Find all asset references and replace with local paths
    # This is a simplified version — handles src, href, srcset
    def replace_url(match):
        url = match.group(1) or match.group(2)
        if not url or url.startswith('data:') or url.startswith('#'):
            return match.group(0)
        local = cache_path(proj, url, '_assets')
        if is_cached(local):
            rel = os.path.relpath(local, os.path.dirname(html_path))
            return match.group(0).replace(url, rel)
        return match.group(0)

    # src="..." and href="..."
    html = re.sub(r'(src|href)=["\']([^"\']+)["\']', replace_url, html)
    # url(...) in CSS
    html = re.sub(r'url\(["\']?([^"\')\s]+)["\']?\)', replace_url, html)

    with open(html_path, 'w') as f:
        f.write(html)


def slug_from_url(url, origin):
    """Extract a human-readable slug from a URL."""
    path = urllib.parse.urlparse(url).path
    path = re.sub(r'^/', '', path)
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
    parser.add_argument('--force', action='store_true', help='Re-download even if cached')
    parser.add_argument('--rate-delay', type=float, default=RATE_DELAY, help='Base delay between requests')
    args = parser.parse_args()

    proj = args.project
    start_url = args.url.rstrip('/')
    origin = urllib.parse.urlparse(start_url).netloc
    depth = args.depth
    max_pages = args.max_pages
    rate_delay = args.rate_delay

    os.makedirs(os.path.join(proj, '.reference', 'cache', '_crawl'), exist_ok=True)
    os.makedirs(os.path.join(proj, '.reference', 'cache', '_assets'), exist_ok=True)
    os.makedirs(os.path.join(proj, 'workflow-output'), exist_ok=True)

    # Crawl queue: (url, current_depth)
    queue = [(start_url, 0)]
    visited = set()
    pages = []
    failed = []
    assets_downloaded = 0
    crawl_start = time.time()

    print(f"Crawling {start_url} (max-pages={max_pages or 'unlimited'}, depth={depth})")

    while queue:
        if max_pages and len(pages) >= max_pages:
            print(f"Reached max-pages limit ({max_pages})")
            break

        url, current_depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        # Download page
        page_cache = cache_path(proj, url, '_crawl')
        if not args.force and is_cached(page_cache):
            print(f"  [cached] {url}")
        else:
            print(f"  [{len(pages)+1}] {url}")
            time.sleep(rate_delay)
            if not download(url, page_cache, rate_delay):
                failed.append({'url': url, 'error': 'download failed'})
                continue

        # Extract slug and title
        slug = slug_from_url(url, origin)
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
            if not args.force and is_cached(asset_path):
                continue
            if download(asset_url, asset_path, rate_delay):
                assets_downloaded += 1

        # Rewrite HTML to use local assets
        rewrite_assets(page_cache, proj)

        # Extract internal links for next depth level
        if current_depth < depth:
            links = extract_links(page_cache, url, origin)
            for link in sorted(links):
                if link not in visited:
                    queue.append((link, current_depth + 1))

    # Write page-inventory.json
    inventory = {
        'siteUrl': start_url,
        'crawledAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'pages': pages,
        'totalPages': len(pages),
        'failedPages': failed,
        'assetsDownloaded': assets_downloaded,
        'maxPages': max_pages or 'unlimited',
        'depth': depth,
    }
    inv_path = os.path.join(proj, 'workflow-output', 'page-inventory.json')
    with open(inv_path, 'w') as f:
        json.dump(inventory, f, indent=2)

    duration = time.time() - crawl_start
    print(f"\n{'='*50}")
    print(f"CRAWL COMPLETE")
    print(f"  Pages:      {len(pages)}")
    print(f"  Assets:     {assets_downloaded}")
    print(f"  Failed:     {len(failed)}")
    print(f"  Duration:   {duration:.0f}s")
    print(f"  Output:     {inv_path}")
    if failed:
        print(f"\nFailed pages:")
        for f_item in failed[:10]:
            print(f"    - {f_item['url']} ({f_item['error']})")


if __name__ == '__main__':
    main()
