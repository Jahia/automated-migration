// mirror_probe.mjs — the LOCAL-MIRROR gate (runs BEFORE the global fidelity gate).
//
// Proves the mirror is TRULY local + faithful:
//   1. serve local-mirror/ from an ephemeral 127.0.0.1 server and render each page
//      with EVERY other origin BLOCKED. GATE = zero blocked *static-asset* requests
//      (css/font/image/script/media — incl. those fetched via JS by extension) that
//      aren't a known tracker HOST or download-residue, AND zero local-server 404s
//      (a ref that points into the mirror but is missing → a real localize hole).
//      Runtime beacons/xhr trackers are ignorable. Also asserts stylesheets applied.
//   1b. RUNTIME REPAIR: URLs composed by JS at render time (Liferay AMD/combo
//      loader, Next.js chunk maps) are invisible to static discovery. On a miss,
//      the probe fetches the asset ONCE from the live origin into
//      local-mirror/runtime-assets/ (ledgered in runtime-manifest.json), then
//      re-renders. Un-fetchable refs (404 live / oversize) become residue —
//      ignorable but logged. Disable with --no-repair.
//   2. mirror fidelity: pixel-diff offline render vs LIVE (both with trackers/consent
//      blocked so the comparison is fair; height delta counted) → mirrorFidelity %.
//
// Writes <slug>.local.png / .live.png / .mfdiff.png + mirror-check.json + a
// self-contained mirror-review.html (slider local↔live + blocked/404 lists).
//
// Usage: node mirror_probe.mjs <project> [maxPages] [--pages a,b] [--all] [--no-live] [--no-repair]
import { chromium } from 'playwright';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import fs from 'fs';
import path from 'path';
import { serveMirror, offlineRoute, loadRuntimeManifest, saveRuntimeManifest, fetchRuntimeAsset } from './mirror_net.mjs';

const argv = process.argv.slice(2);
const flags = {}, pos = [];
const VALUE_FLAGS = new Set(['pages']);
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith('--')) {
    const eq = a.indexOf('=');
    if (eq >= 0) flags[a.slice(2, eq)] = a.slice(eq + 1);
    else { const k = a.slice(2); if (VALUE_FLAGS.has(k) && argv[i + 1] && !argv[i + 1].startsWith('--')) flags[k] = argv[++i]; else flags[k] = true; }
  } else pos.push(a);
}
const proj = pos[0];
const maxPages = parseInt(pos[1] || '4', 10) || 4;
if (!proj) { console.error('usage: mirror_probe.mjs <project> [maxPages] [--pages a,b] [--all] [--no-live]'); process.exit(2); }
const pageSel = typeof flags.pages === 'string' ? flags.pages.split(',').map(s => s.trim()).filter(Boolean) : null;
const doLive = !flags['no-live'];
const doRepair = !flags['no-repair'];

const mirrorDir = path.resolve(`${proj}/workflow-output/local-mirror`);
const outDir = `${proj}/workflow-output/mirror`;
fs.mkdirSync(outDir, { recursive: true });
const mirror = JSON.parse(fs.readFileSync(`${mirrorDir}/mirror.json`, 'utf8'));
const inv = JSON.parse(fs.readFileSync(`${proj}/workflow-output/page-inventory.json`, 'utf8'));
const liveUrl = Object.fromEntries(inv.pages.map(p => [p.slug, p.url]));
const residue = new Set(mirror.residue || []);

// Trackers/consent/analytics/observability — matched against the HOSTNAME only (so a
// real asset path like /segment/hero.css is NOT excused). Plus the recorded residue.
// osano/usercentrics/didomi = consent managers; canarytokens = scrape-detection
// beacons (fetching one FIRES it and exfiltrates the local URL — never repair).
const TRACKER_HOST = /(^|\.)(google-analytics|googletagmanager|doubleclick|facebook|fbcdn|linkedin|twitter|hotjar|segment|trustarc|onetrust|cookiebot|cookielaw|sentry|datadog|optimizely|visualwebsiteoptimizer|marketo|hubspot|clarity\.ms|bing|adservice|youtube|ytimg|osano|usercentrics|didomi|canarytokens)\.|(^|\.)obs\.|(^|\.)consent\./i;
function hostOf(u) { try { return new URL(u).hostname; } catch { return u; } }
const isIgnorable = (u) => TRACKER_HOST.test(hostOf(u)) || residue.has(u) || residue.has(u.replace(/%20/g, ' '));
// localizable static-asset resource types; xhr/fetch handled specially (below).
const STATIC = new Set(['stylesheet', 'font', 'image', 'media', 'imageset', 'script']);
const STATIC_EXT = /\.(css|js|mjs|woff2?|ttf|otf|eot|png|jpe?g|gif|svg|webp|avif|ico|mp4|webm|m4s|ogg|mp3)(\?|#|$)/i;
const isStaticAsset = (b) => STATIC.has(b.type) || ((b.type === 'xhr' || b.type === 'fetch') && STATIC_EXT.test(b.url));

function readPng(p) { return PNG.sync.read(fs.readFileSync(p)); }
function diffPixels(aPath, bPath, outPath) {
  const a = readPng(aPath), b = readPng(bPath);
  const w = Math.min(a.width, b.width), h = Math.min(a.height, b.height);
  const H = Math.max(a.height, b.height);
  const crop = (img) => { if (img.width === w && img.height === h) return img; const o = new PNG({ width: w, height: h }); PNG.bitblt(img, o, 0, 0, w, h, 0, 0); return o; };
  const d = new PNG({ width: w, height: h });
  let n = pixelmatch(crop(a).data, crop(b).data, d.data, w, h, { threshold: 0.1 });
  fs.writeFileSync(outPath, PNG.sync.write(d));
  n += Math.abs(a.height - b.height) * w;                 // count non-overlapping rows as differing
  return { sim: +(100 * (1 - n / (Math.max(1, w * H)))).toFixed(2), dims: `${w}x${h}`, heightDelta: a.height - b.height };
}

let pages;
if (flags.all) pages = mirror.pages;
else if (pageSel) pages = mirror.pages.filter(p => pageSel.includes(p.slug));
else pages = mirror.pages.slice(0, maxPages);
pages = pages.filter(p => !p.error);
if (!pages.length) { console.error('no mirror pages selected'); process.exit(2); }

const manifest = loadRuntimeManifest(mirrorDir);
const { srv, port } = await serveMirror(mirrorDir, manifest);
const base = `http://127.0.0.1:${port}`;
// runtime residue keys: path+query for same-origin misses, absolute URL otherwise
const runtimeIgnorable = (u) => manifest.residue.includes(u.startsWith(base) ? u.slice(base.length) : u);
const excused = (u) => isIgnorable(u) || runtimeIgnorable(u);
const results = [];
const browser = await chromium.launch({ headless: true });

// One offline render: only the local server (+ manifest-fulfilled runtime assets)
// is reachable. Returns the open page + classified misses; caller screenshots/closes.
async function offlineRender(slug) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const blockedRaw = [], local404 = [];
  await page.route('**/*', offlineRoute(base, mirrorDir, manifest, b => blockedRaw.push(b)));
  // a mirror STATIC-ASSET ref that 404s on our own server = a localize hole
  // (missing/mis-pathed css/font/image/script). Runtime nav-prefetch (quicklink)
  // and beacons that 404 locally are not assets → excluded by the same filter.
  page.on('response', (r) => {
    if (!r.url().startsWith(base) || r.status() < 400) return;
    const b = { url: r.url(), type: r.request().resourceType() };
    if (isStaticAsset(b) && !excused(b.url)) local404.push(b.url);
  });
  await page.goto(`${base}/${slug}.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  try { await page.waitForLoadState('load', { timeout: 8000 }); } catch {}
  await page.waitForTimeout(1500);
  const health = await page.evaluate(() => ({
    sheets: document.styleSheets.length,
    rules: [...document.styleSheets].reduce((s, ss) => { try { return s + (ss.cssRules?.length || 0); } catch { return s; } }, 0),
    imgs: [...document.images].filter(i => i.complete && i.naturalWidth > 0).length,
  }));
  const blocked = [...new Map(blockedRaw.map(b => [b.url, b])).values()];
  return { page, health, blocked,
    realMiss: blocked.filter(b => isStaticAsset(b) && !excused(b.url)),
    localMiss: [...new Set(local404)] };
}

for (const pg of pages) {
  const slug = pg.slug;
  const rec = { slug };
  const localPng = `${outDir}/${slug}.local.png`;
  try {
    // ── 1. offline render — runtime-repair to FIXPOINT (repaired JS modules
    // execute and import further modules: Liferay AMD graph, Next.js chunk
    // chains — each round surfaces the next wave until none is left) ──
    let r = await offlineRender(slug);
    for (let round = 0; doRepair && (r.realMiss.length || r.localMiss.length) && round < 5; round++) {
      await r.page.close();
      const origin = liveUrl[slug] ? new URL(liveUrl[slug]).origin : null;
      let saved = 0, residued = 0;
      for (const u of r.localMiss) {
        const key = u.slice(base.length);
        if (!origin) { if (!manifest.residue.includes(key)) manifest.residue.push(key); residued++; continue; }
        (await fetchRuntimeAsset(mirrorDir, manifest, key, origin + key)) === 'saved' ? saved++ : residued++;
      }
      for (const b of r.realMiss) {
        (await fetchRuntimeAsset(mirrorDir, manifest, b.url, b.url)) === 'saved' ? saved++ : residued++;
      }
      saveRuntimeManifest(mirrorDir, manifest);
      rec.runtimeRepaired = (rec.runtimeRepaired || 0) + saved;
      rec.runtimeResidue = (rec.runtimeResidue || 0) + residued;
      console.error(`  ${slug}: runtime-repair round ${round + 1} — ${saved} captured from live, ${residued} residue; re-rendering offline`);
      r = await offlineRender(slug);
      if (saved === 0) break;   // nothing fetchable left — residue now excuses the rest
    }
    rec.offlineRendered = r.health.sheets > 0 && r.health.rules > 0;
    rec.styleSheets = r.health.sheets; rec.cssRules = r.health.rules; rec.localImages = r.health.imgs;
    rec.externalBlocked = r.blocked.length;
    rec.realMiss = r.realMiss.map(b => `${b.type}:${b.url}`).slice(0, 20);
    rec.realMissCount = r.realMiss.length;
    rec.localMiss = r.localMiss.slice(0, 20);
    rec.localMissCount = r.localMiss.length;
    rec.ignorableBlocked = r.blocked.length - r.realMiss.length;
    try { await r.page.screenshot({ path: localPng, fullPage: true }); }
    catch (e) { rec.screenshotError = (e.message || String(e)).split('\n')[0]; }  // tall-page limit ≠ not-local
    await r.page.close();

    // ── 2. mirror fidelity: offline vs live (both with trackers/consent blocked) ──
    if (doLive && liveUrl[slug] && !rec.screenshotError) {
      const lp = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      await lp.route('**/*', (route) => {
        const u = route.request().url();
        if (u.startsWith('http') && isIgnorable(u)) return route.abort();
        return route.continue();
      });
      const livePng = `${outDir}/${slug}.live.png`;
      try {
        await lp.goto(liveUrl[slug], { waitUntil: 'domcontentloaded', timeout: 45000 });
        try { await lp.waitForLoadState('load', { timeout: 15000 }); } catch {}
        await lp.waitForTimeout(3500);
        await lp.screenshot({ path: livePng, fullPage: true });
        const { sim, dims, heightDelta } = diffPixels(localPng, livePng, `${outDir}/${slug}.mfdiff.png`);
        rec.mirrorFidelity = sim; rec.dims = dims; rec.heightDelta = heightDelta;
      } catch (e) { rec.liveError = (e.message || String(e)).split('\n')[0]; }
      await lp.close();
    }
    rec.ok = true;
  } catch (e) {
    rec.ok = false; rec.error = (e.message || String(e)).split('\n')[0];
  }
  results.push(rec);
  const mf = rec.mirrorFidelity != null ? ` | mirror-fidelity ${rec.mirrorFidelity}%` : '';
  const rr = rec.runtimeRepaired != null ? `, ${rec.runtimeRepaired} runtime-repaired` : '';
  console.error(`  ${slug}: ${rec.ok ? (rec.offlineRendered ? 'rendered offline' : 'NOT rendered') + `, ${rec.realMissCount} ext miss, ${rec.localMissCount} local 404${rr}, ${rec.ignorableBlocked} ignored${mf}` : 'FAIL ' + rec.error}`);
}
await browser.close();
srv.close();

const gatePass = results.every(r => r.ok && r.offlineRendered && (r.realMissCount || 0) === 0 && (r.localMissCount || 0) === 0);
fs.writeFileSync(`${outDir}/mirror-check.json`, JSON.stringify({ project: proj, gatePass, pages: results }, null, 2));

const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const okPage = r => r.ok && r.offlineRendered && (r.realMissCount || 0) === 0 && (r.localMissCount || 0) === 0;
const card = r => !r.ok ? `<section class=pg><h2>${esc(r.slug)} — <span class=bad>FAILED</span> ${esc(r.error)}</h2></section>` : `
  <section class=pg>
    <h2>${esc(r.slug)} ${okPage(r) ? '<span class=ok>LOCAL ✓</span>' : '<span class=warn>REVIEW</span>'}
      <small>${r.styleSheets} stylesheets · ${r.localImages} local images · ${r.externalBlocked} external blocked (${r.ignorableBlocked} ignorable, ${r.realMissCount} ext miss, ${r.localMissCount} local 404)${r.runtimeRepaired != null ? ' · ' + r.runtimeRepaired + ' runtime-repaired' : ''}${r.mirrorFidelity != null ? ' · mirror-fidelity ' + r.mirrorFidelity + '%' : ''}</small></h2>
    ${r.mirrorFidelity != null ? `<div class=slider id=s_${esc(r.slug)}>
      <img class=b src="${esc(r.slug)}.live.png"><img class=a src="${esc(r.slug)}.local.png" style="clip-path:inset(0 50% 0 0)">
      <div class=handle></div><input type=range min=0 max=100 value=50 oninput="slide(this)"></div>
      <div class=lg>← LIVE · LOCAL(offline) → · drag</div>` : `<img class=solo src="${esc(r.slug)}.local.png">`}
    ${(r.realMissCount || r.localMissCount)
      ? `<div class=miss><b>Not localized (${r.realMissCount} external asset, ${r.localMissCount} local 404):</b><ul>${[...(r.realMiss || []), ...(r.localMiss || [])].map(u => `<li>${esc(u)}</li>`).join('')}</ul></div>`
      : '<div class=miss ok>✓ no unexpected external assets, no local 404 — truly local (runtime trackers blocked)</div>'}
  </section>`;
const nOk = results.filter(okPage).length;
const html = `<!doctype html><meta charset=utf8><title>Local mirror — ${esc(proj)}</title><style>
 body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 header{padding:16px 24px;background:#171a21;border-bottom:1px solid #2a2f3a;position:sticky;top:0;z-index:9}
 h1{font-size:18px;margin:0}.pg{padding:22px 24px;border-bottom:1px solid #20242e}
 h2{font-size:15px;margin:0 0 10px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}h2 small{color:#9aa4b2;font-weight:400}
 .ok{color:#39d98a}.warn{color:#ffb454}.bad{color:#ff6b6b}
 .slider{position:relative;max-width:1024px;border:1px solid #2a2f3a;background:#fff;overflow:hidden;user-select:none}
 .slider img{display:block;width:100%}.slider .a{position:absolute;top:0;left:0}
 .slider .handle{position:absolute;top:0;bottom:0;left:50%;width:2px;background:#00a1e3;box-shadow:0 0 6px #00a1e3;pointer-events:none}
 .slider input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:ew-resize;margin:0}
 .solo{display:block;max-width:1024px;width:100%;border:1px solid #2a2f3a}
 .lg{color:#9aa4b2;font-size:12px;margin-top:6px}.miss{margin-top:10px;font-size:13px;color:#ffb454}.miss.ok{color:#39d98a}
 .miss li{font-family:ui-monospace,monospace;font-size:12px;color:#cfd6e2;word-break:break-all}
</style>
<header><h1>Local mirror — ${esc(proj)} <span class="${nOk === results.length ? 'ok' : 'warn'}">(${nOk}/${results.length} truly local)</span></h1>
<small style="color:#9aa4b2">Rendered offline (only a local server reachable). GATE = 0 unexpected external static assets + 0 local 404 + stylesheets applied. Slider compares LOCAL(offline) vs LIVE.</small></header>
${results.map(card).join('\n')}
<script>function slide(i){const s=i.closest('.slider'),v=+i.value;s.querySelector('.a').style.clipPath='inset(0 '+(100-v)+'% 0 0)';s.querySelector('.handle').style.left=v+'%';}</script>`;
fs.writeFileSync(`${outDir}/mirror-review.html`, html);

console.log(`\n=== LOCAL MIRROR CHECK — ${proj} ===`);
for (const r of results) {
  if (!r.ok) { console.log(`  ${r.slug}: FAIL ${r.error}`); continue; }
  console.log(`  ${r.slug.padEnd(30)} offline=${r.offlineRendered} extMiss=${r.realMissCount} local404=${r.localMissCount}${r.runtimeRepaired != null ? ` runtimeRepaired=${r.runtimeRepaired}` : ''} ignorable=${r.ignorableBlocked}${r.mirrorFidelity != null ? ` mirrorFidelity=${r.mirrorFidelity}%` : ''}`);
  for (const u of (r.realMiss || [])) console.log(`        ✗ external asset: ${u.slice(0, 120)}`);
  for (const u of (r.localMiss || [])) console.log(`        ✗ local 404: ${u.slice(0, 120)}`);
}
console.log(`\n  GATE: ${gatePass ? 'GREEN — every page renders fully offline (0 external static assets, 0 local 404)' : 'RED — a static asset is missing or still loads from the network'}`);
console.log(`  ▶ REVIEW: open ${outDir}/mirror-review.html\nOutput: ${outDir}/`);
process.exit(gatePass ? 0 : 1);
