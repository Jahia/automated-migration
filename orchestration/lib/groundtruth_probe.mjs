#!/usr/bin/env node
// groundtruth_probe.mjs — THE P1 exit gate (QUALITY-PLAN §2/§5 P1.5).
//
// Every fidelity number before this is self-referential (the analyzer scoring
// its own reconstruction against its own mirror). This is the ground truth:
// the DEPLOYED Jahia page pixel-diffed against the SOURCE local mirror (served
// offline via mirror_net, the same deterministic reference the mirror gate
// certified).
//
// EDIT-ONLY / NO-LIVE DOCTRINE (Julian, 2026-07-04: "aucun test en live"):
// the migration process is EDIT-only and publication is a single FINAL delivery
// act by Julian (publish_site.sh); LIVE is deliberately stale until then. So
// this gate renders the AUTHENTICATED EDIT PREVIEW workspace, NEVER the LIVE
// anonymous page and NEVER after publishing:
//
//     GET $JAHIA_URL/cms/render/default/{lang}/sites/{site}/{pagePath}.html
//         with Basic auth (Playwright context httpCredentials from .env.local)
//
// renders the EDIT (= default) workspace. Measured live (discoverasr,
// 2026-07-04): an EDIT edit is visible here immediately (~0.3 s, no cache
// flush, no publication) and the preview render is byte-near the live render
// (1 220 826 vs 1 220 731 bytes on the same page) — a faithful pixel-diff
// stand-in. Rendering the EDIT state Julian will publish makes the eventual
// LIVE correctness true BY CONSTRUCTION, while keeping this gate entirely off
// the publication/LIVE path (the path that corrupted the run's metadata).
//
// GATE: render fidelity >= threshold (default 99) on EVERY migrated page.
// Masking policy (§2): only regions listed in workflow-output/groundtruth-
// masks.json ([{page:"*"|slug, selector, reason}]) are hidden on BOTH sides.
// Residual diffs must be visible: review.html shows ref | preview | diff per page.
//
// Usage: node groundtruth_probe.mjs <project> <siteKey> [threshold] [--pages a,b]
//        env: JAHIA_URL (or JAHIA_HOST), JAHIA_USER, JAHIA_PASS
import { chromium } from 'playwright';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import fs from 'fs';
import path from 'path';
import { serveMirror, offlineRoute, loadRuntimeManifest } from './mirror_net.mjs';
import { settlePage } from './settle.mjs';
import { stampJson, writeSidecar } from './provenance.mjs';

const [, , projArg, site, thrArg, ...rest] = process.argv;
if (!projArg || !site) {
  console.error('usage: groundtruth_probe.mjs <project> <siteKey> [threshold] [--pages a,b] [--hydrate]');
  process.exit(2);
}
const proj = projArg.replace(/\/$/, '');
const project = path.basename(proj);
const threshold = Number(thrArg) || 99;
let only = null;
const pi = rest.indexOf('--pages');
if (pi >= 0 && rest[pi + 1]) only = rest[pi + 1].split(',');
// --hydrate: let the source JS finish on BOTH captures before the screenshot
// (rule 30 settle applied symmetrically) so JS-driven visibility (rule 35 — an
// empty carousel that its own JS hides when the data XHR fails offline) resolves
// the SAME way on the reference and the preview. Without it (default), each side
// gets only a fixed 3s wait after load, which lets the JS run PARTIALLY and
// inconsistently → height divergence for a non-content reason. Symmetric by
// construction: the same settlePage() runs on ref and live, both fully offline
// outside the Jahia host (rule 26).
const HYDRATE = rest.includes('--hydrate');

const HOST = (process.env.JAHIA_URL || process.env.JAHIA_HOST || 'http://localhost:8080').replace(/\/$/, '');
// Basic-auth credentials for the authenticated EDIT preview render (no LIVE).
// JAHIA_USER may already be in "user:pass" form (_lib.sh combines it); split it.
const RAW_USER = process.env.JAHIA_USER || 'root';
const AUTH_USER = RAW_USER.includes(':') ? RAW_USER.split(':')[0] : RAW_USER;
const AUTH_PASS = RAW_USER.includes(':') ? RAW_USER.split(':').slice(1).join(':')
  : (process.env.JAHIA_PASS || 'root');
const LANG = process.env.JAHIA_PREVIEW_LANG || 'en';
const wo = `${proj}/workflow-output`;
const mirrorDir = `${wo}/local-mirror`;
const outDir = `${wo}/groundtruth`;
fs.mkdirSync(outDir, { recursive: true });

// migrated pages = content-load pages that exist in the mirror
const loadFile = `orchestration/content/${project}.content-load.json`;
if (!fs.existsSync(loadFile)) { console.error(`FAIL: ${loadFile} missing`); process.exit(1); }
const contentLoad = JSON.parse(fs.readFileSync(loadFile, 'utf8'));
let slugs = Object.keys(contentLoad.pages || {})
  .filter(s => fs.existsSync(`${mirrorDir}/${s}.html`));
if (only) slugs = slugs.filter(s => only.includes(s));
if (!slugs.length) { console.error('FAIL: no migrated pages found (content-load ∩ mirror empty)'); process.exit(1); }

// slug -> live page path (sitemap-aware, same mapping as load_content)
const slugMap = {};
const sm = `orchestration/sitemaps/${project}.txt`;
if (fs.existsSync(sm)) {
  for (const line of fs.readFileSync(sm, 'utf8').split('\n')) {
    const l = line.trim();
    if (!l || l.startsWith('#')) continue;
    slugMap[l.split('/').pop().toLowerCase()] = l;
    slugMap[l.toLowerCase()] = l;
  }
}
// AUTHENTICATED EDIT PREVIEW path (workspace=default), NOT the anonymous LIVE
// page. Prefixed with /cms/render/default/{lang} — the render that reflects the
// EDIT state Julian will publish (doctrine: no LIVE, no publication in probes).
const previewPath = (slug) => {
  const base = slug === 'home'
    ? `/sites/${site}/home`
    : `/sites/${site}/home/${slugMap[slug.toLowerCase()] || slug}`;
  return `/cms/render/default/${LANG}${base}.html`;
};

// masking policy (§2): committed, per-site, each entry carries a reason
const masksFile = `${wo}/groundtruth-masks.json`;
const masks = fs.existsSync(masksFile) ? JSON.parse(fs.readFileSync(masksFile, 'utf8')) : [];
const masksFor = (slug) => masks.filter(m => m.page === '*' || m.page === slug);
const maskCss = (slug) => masksFor(slug).map(m => `${m.selector}{visibility:hidden !important}`).join('\n');

// semantic share (quality dial, reported not gated in P1)
const shares = Object.entries(contentLoad.pages)
  .filter(([s, p]) => p.partition && p.partition.semanticLeafShare != null)
  .map(([s, p]) => ({ slug: s, share: p.partition.semanticLeafShare }));

const runtimeManifest = loadRuntimeManifest(mirrorDir);
const { srv: mserver, port: mport } = await serveMirror(mirrorDir, runtimeManifest);
const mbase = `http://127.0.0.1:${mport}`;
const browser = await chromium.launch({ headless: true });
// AUTHENTICATED context for the EDIT preview render (Basic auth). The header
// is sent PREEMPTIVELY via extraHTTPHeaders — httpCredentials alone is NOT
// enough here: /cms/render/default/… returns 404 (not a 401 challenge) to an
// anonymous request, so Playwright would never get prompted to send the
// credentials and the top-level render 404s (measured live 2026-07-04: 404 vs
// 200). httpCredentials is kept as a belt-and-suspenders for any sub-resource
// that DOES issue a 401 challenge. The reference (offline mirror) uses a
// separate unauthenticated context.
const AUTH_HEADER = 'Basic ' + Buffer.from(`${AUTH_USER}:${AUTH_PASS}`).toString('base64');
const previewCtx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  httpCredentials: { username: AUTH_USER, password: AUTH_PASS },
  extraHTTPHeaders: { Authorization: AUTH_HEADER },
});

const readPng = (p) => PNG.sync.read(fs.readFileSync(p));
const results = [];
for (const slug of slugs) {
  const rec = { slug, previewPath: previewPath(slug), masks: masksFor(slug).length };
  try {
    // ── reference: source mirror, offline-deterministic ──
    const ref = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await ref.route('**/*', offlineRoute(mbase, mirrorDir, runtimeManifest, null));
    await ref.goto(`${mbase}/${slug}.html`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    try { await ref.waitForLoadState('load', { timeout: 15000 }); } catch {}
    if (maskCss(slug)) await ref.addStyleTag({ content: maskCss(slug) });
    if (HYDRATE) await settlePage(ref); else await ref.waitForTimeout(3000);
    await ref.screenshot({ path: `${outDir}/${slug}.ref.png`, fullPage: true });
    await ref.close();

    // ── preview: the AUTHENTICATED EDIT-workspace render (NOT anonymous LIVE) ──
    // OFFLINE PARITY: the reference runs fully offline (offlineRoute), so the
    // preview side must not reach the internet either — otherwise external-only
    // widgets (observed live: the OneTrust cookie banner from cdn.cookielaw.org
    // on supercar) render on ONE side and eat ~20 fidelity points. Only the
    // Jahia host is allowed (rule 26 — same offlineRoute both sides). Basic auth
    // rides the authenticated context (httpCredentials), applied automatically
    // to the continued Jahia-host request; no LIVE, no publication.
    const jahiaHost = new URL(HOST).host;
    const live = await previewCtx.newPage();
    const offlineForLive = offlineRoute(mbase, mirrorDir, runtimeManifest, null);
    await live.route('**/*', (route) => {
      const h = new URL(route.request().url()).host;
      if (h === jahiaHost) return route.continue();
      // external request: SAME offline resolution as the reference (mirror-
      // cached fonts/CDN files served, everything else aborted) — the two
      // sides must see an identical world outside the Jahia host
      return offlineForLive(route);
    });
    const resp = await live.goto(HOST + rec.previewPath, { waitUntil: 'domcontentloaded', timeout: 45000 });
    rec.httpStatus = resp ? resp.status() : 0;
    try { await live.waitForLoadState('load', { timeout: 15000 }); } catch {}
    if (maskCss(slug)) await live.addStyleTag({ content: maskCss(slug) });
    if (HYDRATE) await settlePage(live); else await live.waitForTimeout(3000);
    const mainText = await live.evaluate(() =>
      (document.querySelector('main, [role=main], body') || {}).innerText?.trim().length || 0);
    rec.mainChars = mainText;
    await live.screenshot({ path: `${outDir}/${slug}.live.png`, fullPage: true });
    await live.close();

    // ── pixel diff on the common crop; height mismatch is reported, not hidden ──
    const a = readPng(`${outDir}/${slug}.ref.png`);
    const b = readPng(`${outDir}/${slug}.live.png`);
    const w = Math.min(a.width, b.width), h = Math.min(a.height, b.height);
    const crop = (img) => { if (img.width === w && img.height === h) return img; const o = new PNG({ width: w, height: h }); PNG.bitblt(img, o, 0, 0, w, h, 0, 0); return o; };
    const diff = new PNG({ width: w, height: h });
    const n = pixelmatch(crop(a).data, crop(b).data, diff.data, w, h, { threshold: 0.1 });
    fs.writeFileSync(`${outDir}/${slug}.diff.png`, PNG.sync.write(diff));
    rec.fidelity = +(100 * (1 - n / (w * h))).toFixed(2);
    rec.heightDelta = +((Math.abs(a.height - b.height) / Math.max(a.height, 1)) * 100).toFixed(1);
    rec.dims = `${w}x${h} (ref ${a.height}px, preview ${b.height}px)`;
    rec.ok = true;
    rec.pass = rec.fidelity >= threshold && rec.httpStatus === 200 && mainText > 0;
  } catch (e) {
    rec.ok = false; rec.pass = false; rec.error = (e.message || String(e)).split('\n')[0];
  }
  results.push(rec);
  console.error(`  ${slug}: ${rec.ok ? `${rec.fidelity}% (HTTP ${rec.httpStatus}, main ${rec.mainChars} chars, Δh ${rec.heightDelta}%)` : 'FAIL ' + rec.error} ${rec.pass ? '✓' : '✗'}`);
}
await previewCtx.close();
await browser.close();
mserver.close();

const passed = results.filter(r => r.pass).length;
const avgShare = shares.length ? shares.reduce((s, x) => s + x.share, 0) / shares.length : null;
const summary = {
  project, site, threshold, hydrate: HYDRATE, generatedAt: new Date().toISOString(),
  pages: results, passed, total: results.length,
  gatePass: passed === results.length,
  semanticLeafShare: avgShare == null ? null : {
    avg: +avgShare.toFixed(3),
    min: Math.min(...shares.map(x => x.share)),
    perPage: Object.fromEntries(shares.map(x => [x.slug, x.share])),
  },
};
const pageSet = results.map(r => r.slug);
stampJson(summary, 'groundtruth_probe.mjs', pageSet);
fs.writeFileSync(`${outDir}/groundtruth.json`, JSON.stringify(summary, null, 2));
writeSidecar(outDir, 'groundtruth_probe.mjs', pageSet);

// ── review.html: ref | preview | diff per page, worst first ──
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
const rows = results.slice().sort((x, y) => (x.fidelity ?? -1) - (y.fidelity ?? -1)).map(r => `
<section class="${r.pass ? 'pass' : 'fail'}">
 <h2>${esc(r.slug)} — ${r.ok ? r.fidelity + '%' : 'ERROR'} ${r.pass ? '✅' : '❌'}
   <small>HTTP ${esc(r.httpStatus)} · main ${esc(r.mainChars)} chars · Δheight ${esc(r.heightDelta)}% · ${esc(r.dims || '')} · masks ${r.masks}${r.error ? ' · ' + esc(r.error) : ''}</small></h2>
 <div class="tri">
  <figure><figcaption>source mirror (reference)</figcaption><img src="${esc(r.slug)}.ref.png"></figure>
  <figure><figcaption>Jahia preview (EDIT)</figcaption><img src="${esc(r.slug)}.live.png"></figure>
  <figure><figcaption>diff</figcaption><img src="${esc(r.slug)}.diff.png"></figure>
 </div>
</section>`).join('\n');
fs.writeFileSync(`${outDir}/review.html`, `<!doctype html><meta charset="utf-8">
<title>Ground truth — ${esc(project)} → /sites/${esc(site)}</title><style>
 body{margin:0;background:#0f1115;color:#e6e6e6;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;padding:12px 20px;background:#171a21;border-bottom:1px solid #2a2f3a;z-index:9}
 h1{font-size:16px;margin:0} h2{font-size:14px;margin:0 0 8px} h2 small{color:#9aa3b2;font-weight:400}
 section{padding:14px 20px;border-bottom:1px solid #232833} section.fail h2{color:#ff7b72}
 .tri{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
 figure{margin:0} figcaption{color:#9aa3b2;font-size:12px;margin-bottom:4px}
 img{width:100%;border:1px solid #2a2f3a;border-radius:4px}
</style>
<header><h1>GROUND TRUTH — ${passed}/${results.length} pages ≥ ${threshold}% ${summary.gatePass ? '✅' : '❌'}
 · semantic share avg ${avgShare == null ? 'n/a' : (100 * avgShare).toFixed(0) + '%'} (dial, not gated in P1)</h1></header>
${rows}`);

console.error(`\nGROUND TRUTH: ${passed}/${results.length} pages >= ${threshold}% — ${summary.gatePass ? 'PASS' : 'FAIL'} -> ${outDir}/review.html`);
process.exit(summary.gatePass ? 0 : 1);
