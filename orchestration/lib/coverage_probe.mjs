// coverage_probe.mjs — Pre-templatization fidelity/coverage gap analysis.
//
// Renders each page in a REAL browser (Playwright) — unlike the urllib crawler —
// and measures everything the component extraction does NOT capture but that a
// pixel-perfect migration needs: JS-rendered content delta, CSS (rules/tokens/
// media-queries/background-images/fonts), JS behaviours, all asset requests,
// fixed/sticky chrome widgets outside header/footer, and "orphan" content blocks
// not matched by any detected component role. Emits coverage.json + full-page PNGs.
//
// Usage: node orchestration/lib/coverage_probe.mjs <project> [maxPages]
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const proj = process.argv[2];
const maxPages = parseInt(process.argv[3] || '4', 10);
if (!proj) { console.error('usage: coverage_probe.mjs <project> [maxPages]'); process.exit(2); }

const inv = JSON.parse(fs.readFileSync(`${proj}/workflow-output/page-inventory.json`, 'utf8'));
let roleTokens = [];
try {
  const cand = JSON.parse(fs.readFileSync(`${proj}/workflow-output/semantic-candidates.json`, 'utf8'));
  const all = [...(cand.components || []), ...(cand.crossCutting || []), ...(cand.nestedParts || [])];
  roleTokens = [...new Set(all.map(c => (c.role || '').toLowerCase()).filter(Boolean))];
} catch { /* candidates optional */ }

const outDir = `${proj}/workflow-output/coverage`;
fs.mkdirSync(outDir, { recursive: true });

function staticText(cachedAt) {
  try {
    const html = fs.readFileSync(path.join(proj, cachedAt), 'utf8');
    return html.replace(/<script[\s\S]*?<\/script>/gi, ' ')
               .replace(/<style[\s\S]*?<\/style>/gi, ' ')
               .replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().length;
  } catch { return 0; }
}

const pages = inv.pages.slice(0, maxPages);
const results = [];

const browser = await chromium.launch({ headless: true });
for (const p of pages) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let rec = { slug: p.slug, url: p.url };
  try {
    // 'networkidle' never fires on analytics/tracking-heavy sites — use 'load'
    // + a fixed settle wait so JS-rendered content is present.
    await page.goto(p.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    try { await page.waitForLoadState('load', { timeout: 15000 }); } catch {}
    await page.waitForTimeout(4000);

    const data = await page.evaluate((roleTokens) => {
      const txt = el => (el ? (el.innerText || '').replace(/\s+/g, ' ').trim() : '');
      const bodyText = txt(document.body).length;
      const chromeEls = [...document.querySelectorAll('header,footer,nav,[class*="region--header"],[class*="region--footer"]')];
      const chromeText = chromeEls.reduce((s, e) => s + txt(e).length, 0);

      // CSS inventory
      let rules = 0, fontFace = 0, media = 0, opaque = 0;
      const bgUrls = new Set(), fontUrls = new Set();
      for (const ss of document.styleSheets) {
        let cr;
        try { cr = ss.cssRules; } catch { opaque++; continue; }
        if (!cr) continue;
        for (const r of cr) {
          rules++;
          const t = r.cssText || '';
          if (r.type === CSSRule.FONT_FACE_RULE) { fontFace++; (t.match(/url\(([^)]+)\)/g) || []).forEach(u => fontUrls.add(u)); }
          if (r.type === CSSRule.MEDIA_RULE) media++;
          (t.match(/url\((?!['"]?data:)([^)]+)\)/g) || []).forEach(u => { if (/\.(png|jpe?g|webp|gif|svg|avif)/i.test(u)) bgUrls.add(u); });
        }
      }
      const rootProps = (() => { try {
        const cs = getComputedStyle(document.documentElement); let n = 0;
        for (const p of cs) if (p.startsWith('--')) n++; return n;
      } catch { return 0; } })();

      // JS libraries / frameworks
      const w = window;
      const libs = Object.entries({
        jQuery: !!w.jQuery, Splide: !!w.Splide, Swiper: !!w.Swiper, Slick: !!(w.jQuery && w.jQuery.fn && w.jQuery.fn.slick),
        bootstrap: !!w.bootstrap, Alpine: !!w.Alpine, Drupal: !!w.Drupal, React: !!(w.React || document.querySelector('[data-reactroot],#react-root,[data-reactid]')),
        Vue: !!w.Vue, GSAP: !!w.gsap, swiffy: !!document.querySelector('.swiffy-slider'),
      }).filter(([, v]) => v).map(([k]) => k);

      // interactive behaviours needing re-implementation
      const interactive = {
        toggles: document.querySelectorAll('[data-toggle],[data-bs-toggle],[aria-expanded],[data-accordion]').length,
        sliders: document.querySelectorAll('.splide,.swiper,.slick,.swiffy-slider,.carousel,[class*="slider"]').length,
        modals: document.querySelectorAll('[role="dialog"],.modal,[data-modal]').length,
        tabs: document.querySelectorAll('[role="tab"],.tabs,[data-tabs]').length,
        details: document.querySelectorAll('details').length,
        forms: document.querySelectorAll('form').length,
        buttons: document.querySelectorAll('button,[role="button"]').length,
      };

      // fixed/sticky chrome OUTSIDE header/footer (cookie banner, back-to-top, chat...)
      const chrome = [];
      for (const el of document.querySelectorAll('body *')) {
        const pos = getComputedStyle(el).position;
        if ((pos === 'fixed' || pos === 'sticky') && !el.closest('header,footer,nav')) {
          const t = txt(el).slice(0, 60);
          const cls = (el.className && el.className.toString ? el.className.toString() : '').slice(0, 40);
          if (el.offsetWidth > 40 && el.offsetHeight > 20)
            chrome.push({ tag: el.tagName.toLowerCase(), cls, text: t });
        }
      }
      const seen = new Set();
      const chromeUniq = chrome.filter(c => { const k = c.tag + c.cls; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 12);

      // orphan content: direct blocks in main whose class matches NO detected role token
      const main = document.querySelector('main,[class*="region--content"],[role="main"]') || document.body;
      let orphanBlocks = 0, orphanText = 0, coveredText = 0;
      const norm = s => (s || '').toLowerCase();
      const matchesRole = el => {
        const cls = norm(el.className && el.className.toString ? el.className.toString() : '');
        return roleTokens.some(rt => rt && cls.includes(rt));
      };
      for (const el of main.children) {
        if (el.tagName && ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
        const t = txt(el).length;
        if (t < 5) continue;
        if (matchesRole(el) || [...el.querySelectorAll('*')].slice(0, 200).some(matchesRole)) coveredText += t;
        else { orphanBlocks++; orphanText += t; }
      }

      return {
        bodyText, chromeText, contentText: bodyText - chromeText,
        css: { stylesheets: document.styleSheets.length, rules, fontFace, mediaQueries: media, opaqueSheets: opaque,
               backgroundImages: bgUrls.size, cssFonts: fontUrls.size, rootCustomProps: rootProps },
        libs, interactive, chromeWidgets: chromeUniq,
        coverage: { coveredText, orphanText, orphanBlocks,
                    coveragePct: (coveredText + orphanText) ? Math.round(100 * coveredText / (coveredText + orphanText)) : 100 },
      };
    }, roleTokens);

    // asset requests via Resource Timing
    const assets = await page.evaluate(() => {
      const byType = {};
      for (const e of performance.getEntriesByType('resource')) {
        let t = e.initiatorType;
        if (t === 'link' || /\.css(\?|$)/.test(e.name)) t = 'css';
        else if (t === 'script' || /\.js(\?|$)/.test(e.name)) t = 'js';
        else if (/\.(png|jpe?g|webp|gif|svg|avif|ico)(\?|$)/i.test(e.name)) t = 'img';
        else if (/\.(woff2?|ttf|otf|eot)(\?|$)/i.test(e.name)) t = 'font';
        else if (/\.(mp4|webm|mp3|ogg)(\?|$)/i.test(e.name)) t = 'media';
        byType[t] = byType[t] || { count: 0, thirdParty: 0 };
        byType[t].count++;
        try { if (new URL(e.name).host !== location.host) byType[t].thirdParty++; } catch {}
      }
      return byType;
    });

    const sTxt = staticText(p.cachedAt || '');
    rec = {
      ...rec, ok: true,
      staticTextLen: sTxt, renderedTextLen: data.bodyText,
      jsDeltaPct: sTxt ? Math.round(100 * (data.bodyText - sTxt) / Math.max(sTxt, 1)) : null,
      ...data, assets,
    };
    await page.screenshot({ path: `${outDir}/${p.slug}.png`, fullPage: true });
  } catch (e) {
    rec = { ...rec, ok: false, error: (e.message || String(e)).split('\n')[0] };
  }
  results.push(rec);
  await page.close();
  console.error(`  ${p.slug}: ${rec.ok ? 'ok' : 'FAIL ' + rec.error}`);
}
await browser.close();

fs.writeFileSync(`${outDir}/coverage.json`, JSON.stringify({ project: proj, pages: results }, null, 2));

// ── human summary ──
console.log(`\n=== COVERAGE / FIDELITY GAP — ${proj} (${results.length} pages, real browser) ===\n`);
for (const r of results) {
  if (!r.ok) { console.log(`  ${r.slug}: FAIL ${r.error}`); continue; }
  console.log(`▶ ${r.slug}`);
  console.log(`   JS-render delta: static=${r.staticTextLen} rendered=${r.renderedTextLen} chars  (Δ ${r.jsDeltaPct}% ${r.jsDeltaPct > 15 ? '⚠️ JS content the static crawl MISSES' : 'ok'})`);
  console.log(`   component coverage of main content: ${r.coverage.coveragePct}%  (orphan blocks=${r.coverage.orphanBlocks}, orphan text=${r.coverage.orphanText} chars)`);
  console.log(`   CSS: ${r.css.stylesheets} sheets / ${r.css.rules} rules, ${r.css.mediaQueries} @media, ${r.css.fontFace} @font-face, ${r.css.backgroundImages} bg-images, ${r.css.rootCustomProps} :root tokens${r.css.opaqueSheets ? `, ${r.css.opaqueSheets} cross-origin(opaque)` : ''}`);
  console.log(`   JS libs: ${r.libs.join(', ') || 'none detected'}`);
  const iv = r.interactive; console.log(`   interactive: ${iv.sliders} sliders, ${iv.toggles} toggles/accordions, ${iv.tabs} tabs, ${iv.modals} modals, ${iv.forms} forms, ${iv.buttons} buttons`);
  const at = Object.entries(r.assets).map(([k, v]) => `${k}:${v.count}${v.thirdParty ? `(${v.thirdParty} 3rd)` : ''}`).join('  ');
  console.log(`   assets: ${at}`);
  if (r.chromeWidgets.length) console.log(`   ⚠️ fixed/sticky chrome outside header/footer: ${r.chromeWidgets.map(c => `${c.tag}.${c.cls}"${c.text}"`).join(' | ')}`);
  console.log('');
}
console.log(`Output: ${outDir}/coverage.json + per-page full-page PNGs`);
