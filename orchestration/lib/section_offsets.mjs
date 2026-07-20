#!/usr/bin/env node
// section_offsets.mjs — WHERE does the vertical rhythm diverge? (forensic
// instrument, operator doctrine 2026-07-20: offsets are the class AFTER voids
// — content all present, sections sitting 250px off. Pixel bands show the
// smoke; this names the section whose HEIGHT diverges, per page.)
//
// Renders the SOURCE mirror and the AUTHENTICATED EDIT PREVIEW exactly like
// groundtruth_probe (offline route both sides, scripts blocked, same masks),
// then ledgers main>* section geometry side by side:
//   y(top), height, label (tag.class of the section root)
// and prints the aligned table with the height delta per row.
//
// Usage: node section_offsets.mjs <projectPath> <siteKey> --pages a,b
//        env: JAHIA_URL, JAHIA_USER, JAHIA_PASS (same as groundtruth_probe)
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { serveMirror, offlineRoute, loadRuntimeManifest } from './mirror_net.mjs';

const [, , projArg, site, ...rest] = process.argv;
if (!projArg || !site) {
  console.error('usage: section_offsets.mjs <projectPath> <siteKey> --pages a,b');
  process.exit(2);
}
const proj = projArg.replace(/\/$/, '');
let only = null;
const pi = rest.indexOf('--pages');
if (pi >= 0 && rest[pi + 1]) only = rest[pi + 1].split(',');

const HOST = (process.env.JAHIA_URL || process.env.JAHIA_HOST || 'http://localhost:8080').replace(/\/$/, '');
const AUTH_USER = (process.env.JAHIA_USER || 'root').split(':')[0];
const AUTH_PASS = process.env.JAHIA_PASS || 'root';
const LANG = process.env.JAHIA_LANG || 'en';
const wo = `${proj}/workflow-output`;
const mirrorDir = `${wo}/local-mirror`;

const contentLoad = JSON.parse(fs.readFileSync(
  `orchestration/content/${path.basename(proj)}.content-load.json`, 'utf8'));
let slugs = Object.keys(contentLoad.pages || {})
  .filter(s => fs.existsSync(`${mirrorDir}/${s}.html`));
if (only) slugs = slugs.filter(s => only.includes(s));

// same masking policy as groundtruth_probe (defaults + committed site masks)
const DEFAULT_MASKS = [
  { page: '*', selector: 'astro-island[component-url*="Consent"]' },
  { page: '*', selector: '[id*="onetrust"], [class*="onetrust"], [id*="cookiebot"], [id*="CybotCookiebot"]' },
  { page: '*', selector: 'astro-island[component-url*="sonner"]' },
];
const masksFile = `${wo}/groundtruth-masks.json`;
const siteMasks = fs.existsSync(masksFile) ? JSON.parse(fs.readFileSync(masksFile, 'utf8')) : [];
const masks = [...DEFAULT_MASKS, ...siteMasks];
const maskCss = (slug) => masks
  .filter(m => m.page === '*' || m.page === slug)
  .map(m => `${m.selector}{display:none !important}`).join('\n');

// slug -> page path (same rule as groundtruth_probe)
const inv = JSON.parse(fs.readFileSync(`${wo}/page-inventory.json`, 'utf8'));
const siteUrl = (inv.siteUrl || '').replace(/\/+$/, '');
const homeSlug = (inv.pages || []).find(p => (p.url || '').replace(/\/+$/, '') === siteUrl)?.slug
  || (inv.pages || [])[0]?.slug || 'home';
const slugMap = {};
for (const p of inv.pages || []) {
  const l = (p.slug || '');
  slugMap[l.split('/').pop().toLowerCase()] = l;
  slugMap[l.toLowerCase()] = l;
}
const previewPath = (slug) => {
  const base = (slug === 'home' || slug === homeSlug)
    ? `/sites/${site}/home`
    : `/sites/${site}/home/${slugMap[slug.toLowerCase()] || slug}`;
  return `/cms/render/default/${LANG}${base}.html`;
};

const MEASURE = () => {
  const unwrap = (el) => {
    // Jahia wraps each component in a plain area div; descend through
    // class-less single-child wrappers to the real section root
    let cur = el;
    for (let i = 0; i < 4; i++) {
      const kids = [...cur.children];
      if ((cur.className || '') === '' && kids.length === 1) cur = kids[0];
      else break;
    }
    return cur;
  };
  const main = document.querySelector('main') || document.body;
  const rows = [];
  // Jahia wraps components in display:contents divs (NO box) and area divs
  // (a box spanning everything) — collect the TOPMOST elements that own a
  // real box smaller than their container: descend through boxless wrappers
  // and through single-box wrappers that just span all their children.
  const collect = (el, depth) => {
    for (const child of el.children) {
      const r = child.getBoundingClientRect();
      const tag = child.tagName.toLowerCase();
      if (tag === 'script' || tag === 'style' || tag === 'template') continue;
      if (r.height < 2) {
        if (child.children.length && depth < 6) collect(child, depth + 1);
        continue;
      }
      // an area/list wrapper: one box holding MANY boxed sections — descend
      const boxedKids = [...child.children].filter(
        (k) => k.getBoundingClientRect().height >= 2);
      if (boxedKids.length > 1 && (child.className || '') === '' && depth < 6) {
        collect(child, depth + 1);
        continue;
      }
      const root = unwrap(child);
      const cls = (typeof root.className === 'string' ? root.className : '').trim();
      rows.push({
        y: Math.round(r.top + window.scrollY),
        h: Math.round(r.height),
        label: `${root.tagName.toLowerCase()}.${cls.split(/\s+/).slice(0, 3).join('.')}`.slice(0, 70),
        text: (root.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
      });
    }
  };
  collect(main, 0);
  const mr = main.getBoundingClientRect();
  return {
    mainTop: Math.round(mr.top + window.scrollY),
    pageH: Math.round(document.documentElement.scrollHeight),
    headerH: (() => {
      const h = document.querySelector('header');
      return h ? Math.round(h.getBoundingClientRect().height) : 0;
    })(),
    rows,
  };
};

const runtimeManifest = loadRuntimeManifest(mirrorDir);
const { srv, port } = await serveMirror(mirrorDir, runtimeManifest);
const mbase = `http://127.0.0.1:${port}`;
const browser = await chromium.launch({ headless: true });
const AUTH_HEADER = 'Basic ' + Buffer.from(`${AUTH_USER}:${AUTH_PASS}`).toString('base64');
const previewCtx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  httpCredentials: { username: AUTH_USER, password: AUTH_PASS },
  extraHTTPHeaders: { Authorization: AUTH_HEADER },
});
const scriptless = (handler) => (route) => {
  if (route.request().resourceType() === 'script') return route.abort();
  return handler(route);
};
const jahiaHost = new URL(HOST).host;

const report = {};
for (const slug of slugs) {
  try {
    const ref = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await ref.route('**/*', scriptless(offlineRoute(mbase, mirrorDir, runtimeManifest, null)));
    await ref.goto(`${mbase}/${slug}.html`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    try { await ref.waitForLoadState('load', { timeout: 15000 }); } catch {}
    if (maskCss(slug)) await ref.addStyleTag({ content: maskCss(slug) });
    await ref.waitForTimeout(2500);
    const refM = await ref.evaluate(MEASURE);
    await ref.close();

    const live = await previewCtx.newPage();
    const off = offlineRoute(mbase, mirrorDir, runtimeManifest, null);
    await live.route('**/*', scriptless((route) => {
      const h = new URL(route.request().url()).host;
      return h === jahiaHost ? route.continue() : off(route);
    }));
    await live.goto(HOST + previewPath(slug), { waitUntil: 'domcontentloaded', timeout: 45000 });
    try { await live.waitForLoadState('load', { timeout: 15000 }); } catch {}
    if (maskCss(slug)) await live.addStyleTag({ content: maskCss(slug) });
    await live.waitForTimeout(2500);
    const liveM = await live.evaluate(MEASURE);
    await live.close();

    report[slug] = { ref: refM, live: liveM };
    console.log(`\n== ${slug}  pageH ref=${refM.pageH} live=${liveM.pageH} (Δ${liveM.pageH - refM.pageH}) | header ref=${refM.headerH} live=${liveM.headerH} | mainTop ref=${refM.mainTop} live=${liveM.mainTop}`);
    const n = Math.max(refM.rows.length, liveM.rows.length);
    let cum = 0;
    for (let i = 0; i < n; i++) {
      const a = refM.rows[i], b = liveM.rows[i];
      if (a && b) {
        const dh = b.h - a.h;
        cum += dh;
        const flag = Math.abs(dh) > 40 ? '  <== ' : '      ';
        console.log(`${flag}[${i}] ref ${String(a.h).padStart(5)}px  live ${String(b.h).padStart(5)}px  Δh ${String(dh).padStart(5)}  cum ${String(cum).padStart(5)}  ${a.label}  |ref:${a.text.slice(0, 25)}|`);
        if (a.label !== b.label) console.log(`           live label: ${b.label}  |live:${b.text.slice(0, 25)}|`);
      } else if (a) {
        console.log(`  MISS [${i}] ref-only ${a.h}px  ${a.label}  |${a.text.slice(0, 30)}|`);
      } else if (b) {
        console.log(`  EXTRA[${i}] live-only ${b.h}px  ${b.label}  |${b.text.slice(0, 30)}|`);
      }
    }
  } catch (e) {
    console.error(`  ! ${slug}: ${String(e).slice(0, 140)}`);
  }
}
fs.mkdirSync(`${wo}/forensics`, { recursive: true });
fs.writeFileSync(`${wo}/forensics/section-offsets.json`, JSON.stringify(report, null, 1));
console.log(`\nledger -> ${wo}/forensics/section-offsets.json`);
await browser.close();
srv.close();
