#!/usr/bin/env python3
"""Quick re-localize — re-generates HTML files from crawl cache using
existing assets/ files, without fetching anything from the network.
The WAF blocks the live origin, so http_get hangs."""
import hashlib, json, os, re, sys
from bs4 import BeautifulSoup
from urllib.parse import urljoin

proj = sys.argv[1] if len(sys.argv) > 1 else 'projects/ascott'
mirror = os.path.join(proj, 'workflow-output', 'local-mirror')
inv = json.load(open(os.path.join(proj, 'workflow-output', 'page-inventory.json')))
old_mirror = json.load(open(os.path.join(mirror, 'mirror.json')))
pages = inv.get('pages', [])

# Load existing asset index from mirror.json registry
reg = {}
for a in old_mirror.get('reg', []):
    reg[a['url']] = a
# Also scan assets/ directory to build hash→file mapping
asset_files = {}
if os.path.isdir(os.path.join(mirror, 'assets')):
    for f in os.listdir(os.path.join(mirror, 'assets')):
        name, ext = os.path.splitext(f)
        asset_files[name] = f  # hash → filename

KNOWN_EXTS = {'.css','.js','.mjs','.json','.woff2','.woff','.ttf','.otf','.eot',
              '.png','.jpg','.jpeg','.gif','.svg','.webp','.avif','.ico',
              '.mp4','.webm','.m4s','.ogg','.mp3'}

def sha(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:16]

def ext_of(url):
    m = re.search(r'(\.[A-Za-z0-9]{1,5})$', url)
    return m.group(1).lower() if m and m.group(1).lower() in KNOWN_EXTS else ''

count = 0
for page in pages:
    html_path = os.path.join(proj, page.get('cachedAt', ''))
    if not os.path.isfile(html_path):
        continue
    html = open(html_path, errors='replace').read()
    soup = BeautifulSoup(html, 'lxml')
    for b in soup.find_all('base'):
        b.decompose()

    page_url = page['url']
    slug = page['slug']

    for link in soup.find_all('link'):
        href = link.get('href')
        if not href:
            continue
        absu = urljoin(page_url, href)
        h = sha(absu) + ext_of(absu)
        if os.path.isfile(os.path.join(mirror, 'assets', h)):
            link['href'] = 'assets/' + h
            link.attrs.pop('integrity', None)
            link.attrs.pop('crossorigin', None)
        elif href.startswith('http') and ('googletagmanager' in href or 'google-analytics' in href):
            pass  # keep analytics URLs as-is
        elif href.startswith('http'):
            pass  # keep external URLs as-is
        # if already an assets/ path, leave it

    for scr in soup.find_all('script'):
        src = scr.get('src')
        if not src:
            continue
        absu = urljoin(page_url, src)
        h = sha(absu) + ext_of(absu)
        if os.path.isfile(os.path.join(mirror, 'assets', h)):
            scr['src'] = 'assets/' + h
            scr.attrs.pop('integrity', None)
            scr.attrs.pop('crossorigin', None)

    for tag in soup.find_all(['img','source','video','audio']):
        for attr in ('src', 'poster'):
            val = tag.get(attr)
            if not val:
                continue
            absu = urljoin(page_url, val)
            h = sha(absu) + ext_of(absu)
            if os.path.isfile(os.path.join(mirror, 'assets', h)):
                tag[attr] = 'assets/' + h
        # srcset
        srcset = tag.get('srcset')
        if srcset:
            parts = []
            for seg in re.split(r',\s+', srcset.strip()):
                bits = seg.split()
                if bits:
                    absu = urljoin(page_url, bits[0])
                    h = sha(absu) + ext_of(absu)
                    if os.path.isfile(os.path.join(mirror, 'assets', h)):
                        bits[0] = 'assets/' + h
                    parts.append(' '.join(bits))
            tag['srcset'] = ', '.join(parts)

    head = soup.find('head')
    if head is not None:
        for m in head.find_all('meta', charset=True):
            m.decompose()
        meta = soup.new_tag('meta', charset='utf-8')
        head.insert(0, meta)

    out_path = os.path.join(mirror, f'{slug}.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))
    count += 1

print(f'Re-localized {count}/{len(pages)} pages')
