// mirror_net.mjs — shared offline-mirror serving for mirror_probe + reconstruct_probe.
//
// localize_site.py rewrites statically-discoverable refs, but runtime JS composes
// its own URLs (Liferay AMD/combo loader, Next.js chunk maps, quicklink prefetch).
// Those only surface when a real browser renders the mirror. mirror_probe repairs
// them: each miss is fetched ONCE from the live origin into
// local-mirror/runtime-assets/ and recorded in runtime-manifest.json — after which
// every render is fully offline and deterministic.
//
// runtime-manifest.json = { assets: { <key>: {file, type} }, residue: [url…] }
//   key for same-origin requests  = path+query exactly as the page requests it
//                                   (e.g. "/combo/?browserId=chrome&…&/o/x.js")
//   key for cross-origin requests = the absolute URL
//   residue = runtime refs that could not be captured (404 on live / over size
//   cap / network error) — honest ledger, treated as ignorable by the gate.
import fs from 'fs';
import http from 'http';
import path from 'path';
import crypto from 'crypto';

export const MIME = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.gif': 'image/gif', '.webp': 'image/webp', '.avif': 'image/avif', '.ico': 'image/x-icon',
  '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.otf': 'font/otf', '.eot': 'application/vnd.ms-fontobject',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.ogg': 'audio/ogg', '.mp3': 'audio/mpeg' };

const MANIFEST = 'runtime-manifest.json';

// Default gate sample = one representative page PER TEMPLATE CLUSTER (diverse
// layouts), not the first N inventory pages (which can all be the same template —
// supercar's fr-FR/home/en was one layout in two locales). Falls back to first-N
// when semantic-templates.json is absent. Fills leftover budget from the biggest
// clusters so a large maxPages still gets breadth. Returns an ordered slug list.
export function clusterSample(proj, availableSlugs, maxPages) {
  const avail = new Set(availableSlugs);
  try {
    const t = JSON.parse(fs.readFileSync(path.join(proj, 'workflow-output', 'semantic-templates.json'), 'utf8'));
    const clusters = (t.clusters || []).map(c => (c.pages || []).filter(s => avail.has(s)))
      .filter(ps => ps.length).sort((a, b) => b.length - a.length);
    if (!clusters.length) return availableSlugs.slice(0, maxPages);
    const picked = [];
    for (const ps of clusters) if (picked.length < maxPages && !picked.includes(ps[0])) picked.push(ps[0]);
    // budget left over → add the next unused page from the largest clusters
    let i = 1;
    while (picked.length < maxPages) {
      let added = false;
      for (const ps of clusters) {
        if (ps[i] && !picked.includes(ps[i])) { picked.push(ps[i]); added = true; if (picked.length >= maxPages) break; }
      }
      if (!added) break;
      i++;
    }
    return picked;
  } catch { return availableSlugs.slice(0, maxPages); }
}

export function loadRuntimeManifest(mirrorDir) {
  try {
    const m = JSON.parse(fs.readFileSync(path.join(mirrorDir, MANIFEST), 'utf8'));
    return { assets: m.assets || {}, residue: m.residue || [] };
  } catch { return { assets: {}, residue: [] }; }
}

export function saveRuntimeManifest(mirrorDir, man) {
  fs.writeFileSync(path.join(mirrorDir, MANIFEST), JSON.stringify(man, null, 2));
}

// text types get an explicit charset: localized HTML often has its <meta charset>
// pushed past the browser's 1024-byte sniff window by rewritten <link> tags —
// without this header the page decodes as Latin-1 (mojibake in accented text).
const TEXTUAL = /^(text\/|application\/(json|javascript))/;
function sendFile(res, fp, ctype) {
  fs.readFile(fp, (e, data) => {
    if (e) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': TEXTUAL.test(ctype) ? `${ctype}; charset=utf-8` : ctype });
    res.end(data);
  });
}

// Ephemeral 127.0.0.1 server over the mirror dir. Exact path+query hits the
// runtime manifest first (combo/loader URLs are query-addressed); then plain
// files (query stripped). Path traversal is confined to the mirror root.
export function serveMirror(dir, manifest) {
  const root = path.resolve(dir);
  const rootPfx = root.endsWith(path.sep) ? root : root + path.sep;
  const inRoot = (fp) => fp === root || fp.startsWith(rootPfx);
  const srv = http.createServer((req, res) => {
    const raw = req.url || '/';
    const hit = manifest && manifest.assets[raw];
    if (hit) {
      const fp = path.resolve(path.join(root, hit.file));
      if (inRoot(fp)) return sendFile(res, fp, hit.type || 'application/octet-stream');
    }
    let p;
    try { p = decodeURIComponent(raw.split('?')[0]); } catch { res.writeHead(400); return res.end(); }
    if (p === '/') p = '/index.html';
    const fp = path.resolve(path.join(root, p));
    if (!inRoot(fp)) { res.writeHead(403); return res.end(); }
    sendFile(res, fp, MIME[path.extname(fp).toLowerCase()] || 'application/octet-stream');
  });
  return new Promise(r => srv.listen(0, '127.0.0.1', () => r({ srv, port: srv.address().port })));
}

// page.route handler: local server → continue; cross-origin captured in the
// manifest → fulfilled from disk (still offline); anything else → abort
// (recorded via onBlock). file:// and data: pass through.
export function offlineRoute(base, mirrorDir, manifest, onBlock) {
  return (route) => {
    const u = route.request().url();
    if (u.startsWith(base)) return route.continue();
    if (u.startsWith('http')) {
      const hit = manifest && manifest.assets[u];
      if (hit) {
        try {
          const fp = path.resolve(path.join(path.resolve(mirrorDir), hit.file));
          const body = fs.readFileSync(fp);
          return route.fulfill({ status: 200, contentType: hit.type || 'application/octet-stream', body });
        } catch { /* fall through to abort */ }
      }
      if (onBlock) onBlock({ url: u, type: route.request().resourceType() });
      return route.abort();
    }
    return route.continue();
  };
}

const KNOWN_EXTS = new Set(['css', 'js', 'mjs', 'json', 'woff2', 'woff', 'ttf', 'otf', 'eot',
  'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'avif', 'ico', 'mp4', 'webm', 'ogg', 'mp3']);
const CT_EXT = { 'text/css': 'css', 'text/javascript': 'js', 'application/javascript': 'js',
  'application/x-javascript': 'js', 'application/json': 'json', 'font/woff2': 'woff2', 'font/woff': 'woff',
  'font/ttf': 'ttf', 'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/svg+xml': 'svg',
  'image/webp': 'webp', 'image/avif': 'avif', 'video/mp4': 'mp4', 'video/webm': 'webm' };
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

// resource kinds that must NOT come back as an HTML document — a 200 text/html body
// for a script/style/font/image/media request is a soft-404 / login wall / bot page.
// Saving it would poison the manifest (fulfilled with status 200 on every later render).
const NONHTML_KINDS = new Set(['script', 'stylesheet', 'font', 'image', 'media', 'imageset']);

// Percent-encode unsafe chars (spaces, parens, non-ASCII) in a URL's path/query
// so the live fetch's request line is valid — a raw space is a hard 400. Encoding
// is idempotent (an already-encoded `%20` is preserved). The manifest KEY is left
// untouched (it must stay byte-exact to what the page requests); only the outbound
// fetch URL is canonicalised. Falls back to the raw string if URL parsing fails.
export function normalizeFetchUrl(u) {
  try {
    const p = new URL(u);
    p.pathname = p.pathname.split('/').map(s => encodeURIComponent(decodeURIComponent(s))).join('/');
    return p.toString();
  } catch { return u; }
}

// Fetch one runtime-discovered asset from the live origin into the mirror.
// Returns 'saved' | 'residue' (404/oversize/network/soft-404 — recorded in the ledger).
// expectKind = the requesting resourceType (from the blocked request), used to reject
// content-type mismatches. capBytes defaults higher for media (hero videos/fonts).
export async function fetchRuntimeAsset(mirrorDir, manifest, key, absUrl, expectKind = 'other', capBytes = null) {
  const cap = capBytes != null ? capBytes : (expectKind === 'media' ? 50 * 1024 * 1024 : 30 * 1024 * 1024);
  const toResidue = () => { if (!manifest.residue.includes(key)) manifest.residue.push(key); return 'residue'; };
  try {
    const r = await fetch(normalizeFetchUrl(absUrl), {
      redirect: 'follow',
      headers: { 'User-Agent': UA, 'Accept': '*/*' },
      signal: AbortSignal.timeout(30000),
    });
    if (!r.ok) return toResidue();
    const ct = (r.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
    // soft-404 guard: an HTML body for a non-HTML request is an error page, not the asset
    if (ct.startsWith('text/html') && NONHTML_KINDS.has(expectKind)) return toResidue();
    const buf = Buffer.from(await r.arrayBuffer());
    if (buf.length > cap) return toResidue();
    let ext = (key.split('?')[0].match(/\.([a-z0-9]+)$/i) || [])[1]?.toLowerCase();
    if (!ext || !KNOWN_EXTS.has(ext)) ext = CT_EXT[ct] || 'bin';
    const file = `runtime-assets/${crypto.createHash('sha1').update(key).digest('hex')}.${ext}`;
    fs.mkdirSync(path.join(mirrorDir, 'runtime-assets'), { recursive: true });
    fs.writeFileSync(path.join(mirrorDir, file), buf);
    manifest.assets[key] = { file, type: ct || MIME['.' + ext] || 'application/octet-stream' };
    return 'saved';
  } catch { return toResidue(); }
}

// ── EDIT-preview path resolution (2026-07-20): the SINGLE implementation ────
// Duplicating GT's sitemap-aware slug mapping cost a full forensic detour —
// section_offsets copied only the inventory half, resolved nested pages
// (sending/delivery-rates) to flat 404 paths, and the blank renders read as
// "pages vanished". Every instrument resolves through THIS helper now.
import fs2 from 'fs';
export function previewPathResolver(project, wo, site, lang = 'en') {
  const slugMap = {};
  const sm = `orchestration/sitemaps/${project}.txt`;
  if (fs2.existsSync(sm)) {
    for (const line of fs2.readFileSync(sm, 'utf8').split('\n')) {
      const l = line.trim();
      if (!l || l.startsWith('#')) continue;
      slugMap[l.split('/').pop().toLowerCase()] = l;
      slugMap[l.toLowerCase()] = l;
    }
  }
  const inv = JSON.parse(fs2.readFileSync(`${wo}/page-inventory.json`, 'utf8'));
  const siteUrl = (inv.siteUrl || '').replace(/\/+$/, '');
  const homeSlug = (inv.pages || []).find(
    (p) => (p.url || '').replace(/\/+$/, '') === siteUrl)?.slug
    || (inv.pages || [])[0]?.slug || 'home';
  for (const p of inv.pages || []) {
    const l = (p.slug || '');
    if (!l) continue;
    if (!(l.split('/').pop().toLowerCase() in slugMap)) {
      slugMap[l.split('/').pop().toLowerCase()] = l;
    }
    if (!(l.toLowerCase() in slugMap)) slugMap[l.toLowerCase()] = l;
  }
  return (slug) => {
    const base = (slug === 'home' || slug === homeSlug)
      ? `/sites/${site}/home`
      : `/sites/${site}/home/${slugMap[slug.toLowerCase()] || slug}`;
    return `/cms/render/default/${lang}${base}.html`;
  };
}
