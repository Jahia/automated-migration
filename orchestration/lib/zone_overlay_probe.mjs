#!/usr/bin/env node
/**
 * zone_overlay_probe — screenshot every page WITH its detected zone/component
 * boundaries drawn on top, so a human JUDGES the decomposition granularity.
 *
 * Input: the <slug>.overlay.html files written by zone_to_contentload.py --overlay
 * (the localized page markup + data-zt/data-zc tags + boundary CSS). We serve them
 * through the same offline mirror server the fidelity probes use (assets resolve,
 * WAF-free), render full-page, and screenshot. Output: workflow-output/zone-overlay/
 * <slug>.png + an index.html gallery with the color legend.
 *
 * A pixel-diff would be useless here (skeletons are byte-exact source markup), so
 * the deliverable is the BOUNDARY view, not a similarity score.
 *
 * Usage: node zone_overlay_probe.mjs projects/<proj> [--pages a,b]
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { serveMirror, offlineRoute, loadRuntimeManifest } from './mirror_net.mjs';

const argv = process.argv.slice(2);
const proj = argv.find((a) => !a.startsWith('--'));
if (!proj) { console.error('usage: zone_overlay_probe.mjs projects/<proj> [--pages a,b]'); process.exit(2); }
const pagesFlag = (() => { const i = argv.indexOf('--pages'); return i >= 0 ? argv[i + 1].split(',').map((s) => s.trim()) : null; })();

const mirrorDir = `${proj}/workflow-output/local-mirror`;
const outDir = `${proj}/workflow-output/zone-overlay`;
fs.mkdirSync(outDir, { recursive: true });

if (!fs.existsSync(`${mirrorDir}/mirror.json`)) {
  console.error(`  ! no local mirror at ${mirrorDir} — run localize first`); process.exit(1);
}
let slugs = fs.readdirSync(mirrorDir)
  .filter((f) => f.endsWith('.overlay.html'))
  .map((f) => f.replace(/\.overlay\.html$/, ''));
if (pagesFlag) slugs = slugs.filter((s) => pagesFlag.includes(s));
if (!slugs.length) { console.error('  ! no <slug>.overlay.html files — run zone_to_contentload --overlay first'); process.exit(1); }

const runtimeManifest = loadRuntimeManifest(mirrorDir);
const { srv, port } = await serveMirror(mirrorDir, runtimeManifest);
const mbase = `http://127.0.0.1:${port}`;
const browser = await chromium.launch();
const done = [];
for (const slug of slugs) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  try {
    await page.route('**/*', offlineRoute(mbase, mirrorDir, runtimeManifest, null));
    await page.goto(`${mbase}/${slug}.overlay.html`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${outDir}/${slug}.png`, fullPage: true });
    // count boundaries by category for a per-page granularity readout
    const counts = await page.evaluate(() => {
      const c = {};
      document.querySelectorAll('[data-zc]').forEach((e) => { const k = e.getAttribute('data-zc'); c[k] = (c[k] || 0) + 1; });
      return c;
    });
    done.push({ slug, counts });
    console.error(`  ✓ ${slug}  ${JSON.stringify(counts)}`);
  } catch (e) {
    console.error(`  ! ${slug}: ${e.message}`);
  } finally {
    await page.close();
  }
}
await browser.close();
srv.close();

// gallery
const LEG = [['chrome', '#8a8f98', 'chrome (nav/footer)'], ['cont', '#0E7A6B', 'container'],
  ['atom', '#4A55C7', 'atome'], ['generic', '#B4590B', 'section générique'], ['raw', '#C0392B', 'rawHtml verbatim']];
const legend = LEG.map(([, c, l]) => `<span style="border-left:14px solid ${c};padding:2px 8px;margin-right:6px">${l}</span>`).join('');
const cards = done.map((d) => {
  const tot = Object.values(d.counts).reduce((a, b) => a + b, 0);
  const gen = (d.counts.generic || 0) + (d.counts.raw || 0);
  const pct = tot ? Math.round((100 * gen) / tot) : 0;
  // link the thumbnail to the INTERACTIVE overlay (hover → instance count + other
  // pages + template banner) — served alongside from the mirror dir.
  const live = `../local-mirror/${d.slug}.overlay.html`;
  return `<section style="margin:26px 0"><h2 style="font:600 15px monospace">${d.slug}
    <span style="color:#697386;font-weight:400"> · ${tot} blocs · ${pct}% génériques</span>
    <a href="${live}" target="_blank" style="font:400 12px sans-serif;color:#0077bf;margin-left:8px">▶ interactif (survol) ↗</a></h2>
    <a href="${live}" target="_blank"><img src="${d.slug}.png" style="max-width:100%;border:1px solid #ddd"/></a></section>`;
}).join('');
fs.writeFileSync(`${outDir}/index.html`,
  `<!doctype html><meta charset=utf-8><title>Zone overlay — ${path.basename(proj)}</title>
   <body style="font-family:-apple-system,sans-serif;max-width:1100px;margin:0 auto;padding:24px">
   <h1>Cartes de zonage — ${path.basename(proj)}</h1>
   <p style="color:#697386;font-size:13px">Vignette = aperçu des frontières. <b>Clique une page pour la version interactive</b> : bandeau <b>Template</b> en haut, et au <b>survol</b> d'un composant → nombre d'instances + autres pages qui le référencent.</p>
   <div style="position:sticky;top:0;background:#fff;padding:10px 0;border-bottom:1px solid #eee;font-size:13px;z-index:9">${legend}</div>
   ${cards}</body>`);
console.error(`\n  zone-overlay: ${done.length}/${slugs.length} page(s) -> ${outDir}/index.html`);
process.exit(done.length ? 0 : 1);
