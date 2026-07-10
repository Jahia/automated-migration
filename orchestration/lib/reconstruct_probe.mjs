// reconstruct_probe.mjs — Round-trip fidelity gate (BEFORE Jahia templatization).
//
// The decisive completeness test: reconstruct each sample page from ONLY the
// elements our extraction captured (the detected component nodes), render it, and
// pixel-diff against the live source. If the reconstruction is identical, we have
// proof the extraction is complete; the diff localises exactly what is NOT captured
// (orphan content, section backgrounds, chrome, JS-injected zones) — i.e. the part
// the template + asset import must supply. Runs green/red as an orchestrator gate.
//
// Method: render the source, then in the SAME live DOM mask everything that is not
// inside a detected component (visibility:hidden keeps layout boxes so nothing
// reflows), screenshot again, and pixelmatch the two. similarity = 1 - diffPixels.
//
// Usage:
//   node reconstruct_probe.mjs <project> [maxPages] [threshold] [--pages a,b,c] [--all]
//   --pages home,about-us   pick EXACTLY these page slugs (your sample)
//   --all                   every page in the inventory
// Always writes a self-contained visual review at <out>/review.html.
import { chromium } from 'playwright';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import fs from 'fs';
import path from 'path';
import { serveMirror, offlineRoute, loadRuntimeManifest, clusterSample } from './mirror_net.mjs';
import { stampJson, writeSidecar } from './provenance.mjs';

const argv = process.argv.slice(2);
const flags = {}, pos = [];
const VALUE_FLAGS = new Set(['pages']);       // flags that take a value (space or =)
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith('--')) {
    const eq = a.indexOf('=');
    if (eq >= 0) flags[a.slice(2, eq)] = a.slice(eq + 1);
    else {
      const k = a.slice(2);
      if (VALUE_FLAGS.has(k) && argv[i + 1] && !argv[i + 1].startsWith('--')) flags[k] = argv[++i];
      else flags[k] = true;
    }
  } else pos.push(a);
}
const proj = pos[0];
const maxPages = parseInt(pos[1] || '4', 10) || 4;
const threshold = parseFloat(pos[2] || '95'); // % content coverage to pass
if (!proj) { console.error('usage: reconstruct_probe.mjs <project> [maxPages] [threshold] [--pages a,b] [--all]'); process.exit(2); }
const pageSel = typeof flags.pages === 'string' ? flags.pages.split(',').map(s => s.trim()).filter(Boolean) : null;

const inv = JSON.parse(fs.readFileSync(`${proj}/workflow-output/page-inventory.json`, 'utf8'));
let sxaMode = false;
try { sxaMode = JSON.parse(fs.readFileSync(`${proj}/workflow-output/semantic-candidates.json`, 'utf8')).sxaMode; } catch {}
const outDir = `${proj}/workflow-output/reconstruct`;
fs.mkdirSync(outDir, { recursive: true });

// role -> Jahia nodeType (overlay labels), from the assembled manifest if present.
const roleType = {};
try {
  const man = JSON.parse(fs.readFileSync(`${proj}/workflow-output/component-manifest.json`, 'utf8'));
  for (const c of [...(man.components || []), ...(man.crossCutting || [])]) {
    const roles = c.coversRoles || (c.coversRole ? [c.coversRole] : []);
    for (const r of roles) if (!(r in roleType)) roleType[r] = c.nodeType;
  }
} catch { /* manifest optional — labels fall back to the raw role */ }

// in-browser component identification — mirrors semantic_extract's altitude rules.
// Passed as a real function to page.evaluate (NOT a string).
const identify = (sxaMode) => {
  const txt = el => (el.innerText || '').replace(/\s+/g, ' ').trim();
  // headings are NOT only <h1>-<h6>: design-system sites render visual headings as
  // <p>/<span>/<div> with a typography-heading class or ARIA. Must match
  // semantic_extract._is_heading so the gate measures what the extractor extracts.
  const HEADING_CLS = /(?:^|[-_ ])(heading|headline)(?:$|[-_ 0-9])/i;
  const isHeadingEl = el => /^H[1-6]$/.test(el.tagName)
    || el.getAttribute('role') === 'heading' || el.hasAttribute('aria-level')
    || (['P', 'SPAN', 'DIV'].includes(el.tagName) && HEADING_CLS.test(el.className || ''));
  const hasHeading = el => /^H[1-6]$/.test(el.tagName) ? true : !!el.querySelector('h1,h2,h3,h4,h5,h6,[role="heading"],[aria-level]') || [...el.querySelectorAll('p,span,div')].some(isHeadingEl);
  const hasContent = el => hasHeading(el) || el.querySelector('img,picture,video') || el.querySelector('a[href]') || txt(el).length > 40;
  const isBlock = el => el.nodeType === 1 && ['DIV', 'SECTION', 'ARTICLE', 'ASIDE', 'FORM', 'UL', 'OL', 'HEADER', 'FOOTER', 'NAV'].includes(el.tagName) && hasContent(el);
  // layout-class detection + CSS-module hash strip — mirror semantic_extract so the
  // in-browser row signature groups siblings the SAME way the extractor does
  // (Next.js: call_to_action_card__9Pqm4 → callToActionCard; drop lg:col-span-8).
  const LAYOUT_EXACT = new Set(['component', 'container', 'container-fluid', 'row', 'grid',
    'inner', 'wrapper', 'content-wrapper', 'clearfix', 'flex', 'd-flex', 'no-gutters', 'col', 'slide',
    'swiper', 'swiper-wrapper']);
  const LAYOUT_RE = /^(col-|offset-|order-|[mp][trblxyse]?-|g[xy]?-|gap-|w-|h-|bg-|text-|justify-|align-|flex-|rounded|shadow|border|position-|overflow-|z-|d-(sm|md|lg|xl|xxl)-|coh-|ssa-|splide|lfr-|portlet-|clay-|atb-|(sm|md|lg|xl|xxl):|col-span-|col-start-|col-end-)/;
  const isLayout = t => LAYOUT_EXACT.has(t) || LAYOUT_RE.test(t);
  const cleanTok = t => { const s = t.indexOf('__') >= 0 ? t.slice(0, t.indexOf('__')) : t; return s; };
  const firstSem = el => {
    const cls = (el.className || '').toString().split(/\s+/).filter(Boolean).map(cleanTok);
    return cls.filter(c => !isLayout(c.toLowerCase()))[0] || '';
  };
  const ownHeading = node => {
    const bk = [...node.children].filter(isBlock);
    const heads = [...node.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"],[aria-level]'),
      ...[...node.querySelectorAll('p,span,div')].filter(isHeadingEl)];
    return heads.some(h => h.textContent.trim() && !bk.some(b => b.contains(h)));
  };
  // a wrapper with its OWN visible background = a banner/hero/coloured section = one
  // component (matches semantic_extract._has_visual_bg — static signal, no computed
  // style, so the model and this measurement agree).
  const BG_CLS = /(?:^|[-_ ])(hero|banner|masthead|jumbotron|full[-_]?size|promo|cta)(?:$|[-_ ])/i;
  const BG_SKIP = /^(transparent|none|inherit|initial|unset|currentcolor|#fff(fff)?\b|white|rgba?\(\s*255\s*,\s*255\s*,\s*255|rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0)/i;
  const hasBg = el => {
    const style = (el.getAttribute('style') || '').toLowerCase();
    const m = /background(?:-color|-image|)\s*:\s*([^;]+)/.exec(style);
    if (m && m[1].trim() && !BG_SKIP.test(m[1].trim())) return true;
    return BG_CLS.test(el.className || '');
  };
  function row(node, depth) {
    if (depth > 7) return [node];
    const bc = [...node.children].filter(isBlock);
    if (bc.length === 0) return [node];
    if (depth > 0 && (ownHeading(node) || hasBg(node))) return [node];  // titled section OR coloured band = one component
    if (bc.length === 1) return row(bc[0], depth + 1);
    const sig = {}; bc.forEach(c => { const k = c.tagName + '.' + firstSem(c); sig[k] = (sig[k] || 0) + 1; });
    const top = Math.max(...Object.values(sig));
    if (top >= 3 && top >= 0.6 * bc.length) return [node];
    return bc.flatMap(c => row(c, depth + 1));
  }
  let comps = [];
  if (sxaMode) comps = [...document.querySelectorAll('.component')].filter(c => !(c.parentElement && c.parentElement.closest('.component')));
  else {
    comps = [...document.querySelectorAll('header,footer,nav')];
    const main = document.querySelector('main,[class*="region--content"],[role="main"]') || document.body;
    comps = comps.concat(row(main, 0).filter(n => !['HEADER', 'FOOTER', 'NAV'].includes(n.tagName)));
  }
  // content coverage: fraction of visible body text that lives inside a component.
  // Count TOP-LEVEL components only (a top-level comp's innerText already includes
  // its nested component descendants) so text is not double-counted.
  const topLevel = comps.filter(c => !comps.some(o => o !== c && o.contains(c)));
  const bodyText = txt(document.body).length;
  const coveredText = topLevel.reduce((s, c) => s + txt(c).length, 0);

  // list the ACTUAL uncaptured content: text-bearing elements not in any component.
  // Classify known non-content chrome (cookie consent, a11y skip-links, lang switch)
  // as IGNORABLE — it is not an extraction failure (handled by a Jahia module /
  // the template), so it must not fail the content-coverage gate.
  const IGNORE = /cookie|consent|trustarc|privacy|confidential|pr[ée]f[ée]rence|skip to (main )?content|aller au contenu|select language|choisir la langue|visually-hidden|sr-only|back to top|retour en haut/i;
  // non-rendered tags that can hold text but never paint (Next.js/SSR often puts a
  // <title> and hydration <div style=display:none> JSON blobs in the body).
  const NONRENDER = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TITLE', 'META', 'LINK', 'HEAD', 'TEMPLATE']);
  // truly non-rendered: removed from layout or explicitly hidden. NB: opacity:0 is
  // NOT treated as hidden — scroll-reveal libraries (AOS/ScrollReveal/wow.js) start
  // real below-the-fold content at opacity:0, and it still occupies layout; bucketing
  // it as hidden would drop real orphans from the actionable list while it drags
  // coverage down (contradictory gate output). It still has a box, so it counts.
  const isVisible = el => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse') return false;
    if (el.offsetParent === null && s.position !== 'fixed') return false;   // detached from layout
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const inComp = el => comps.some(c => c === el || c.contains(el));
  const orphanSamples = []; const seen = new Set();
  let ignorableChars = 0, realOrphanChars = 0, hiddenChars = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (NONRENDER.has(el.tagName) || inComp(el)) continue;
    let own = ''; for (const n of el.childNodes) if (n.nodeType === 3) own += n.textContent;
    own = own.replace(/\s+/g, ' ').trim();
    if (own.length < 12 || seen.has(own)) continue;
    seen.add(own);
    const cls = (el.className || '').toString();
    // hidden text (display:none / zero-box / SSR hydration data) is neither a real
    // orphan nor visible chrome — bucket separately so it can't inflate realOrphanChars.
    if (!isVisible(el)) { hiddenChars += own.length; orphanSamples.push({ tag: el.tagName.toLowerCase(), cls: cls.slice(0, 40), text: own.slice(0, 80), ignorable: true, hidden: true }); continue; }
    const ignorable = IGNORE.test(own) || IGNORE.test(cls) || !!el.closest('[class*="trustarc"],[id*="onetrust"],[class*="cookie"],[aria-label*="cookie" i]');
    if (ignorable) ignorableChars += own.length; else realOrphanChars += own.length;
    orphanSamples.push({ tag: el.tagName.toLowerCase(), cls: cls.slice(0, 40), text: own.slice(0, 80), ignorable });
  }

  // component bounding boxes for the overlay map (document coords; deviceScale=1 →
  // 1 CSS px = 1 image px). Collected BEFORE masking (layout is identical either way).
  const roleOf = el => {
    if (['HEADER', 'FOOTER', 'NAV'].includes(el.tagName)) return el.tagName.toLowerCase();
    return firstSem(el) || el.tagName.toLowerCase();
  };
  const docW = document.documentElement.scrollWidth, docH = document.documentElement.scrollHeight;
  const boxes = comps.map(c => {
    const r = c.getBoundingClientRect();
    return {
      role: roleOf(c), tag: c.tagName.toLowerCase(),
      x: r.left + window.scrollX, y: r.top + window.scrollY, w: r.width, h: r.height,
      top: !comps.some(o => o !== c && o.contains(c)),
    };
  }).filter(b => b.w > 4 && b.h > 4);

  document.body.style.visibility = 'hidden';
  comps.forEach(c => { c.style.visibility = 'visible'; });
  // content coverage credits ignorable chrome (not our content to capture)
  const denom = Math.max(1, bodyText - ignorableChars);
  return {
    nComps: comps.length,
    bodyText,
    coveredText,
    contentCoveragePct: Math.min(100, Math.round(100 * coveredText / denom)),
    realOrphanChars: realOrphanChars,
    ignorableChars,
    hiddenChars,
    orphanSamples: orphanSamples.slice(0, 20),
    boxes, docW, docH,
  };
};

// Serve the local mirror so the fidelity gate renders OFFLINE + deterministically
// (no live dependency / WAF timeouts) when localize_site.py has run.
const mirrorDir = `${proj}/workflow-output/local-mirror`;
const useMirror = fs.existsSync(`${mirrorDir}/mirror.json`);
// runtime-manifest.json (written by mirror_probe's repair pass) lets JS-composed
// URLs (Liferay combo loader, Next.js chunks) resolve offline here too.
const runtimeManifest = useMirror ? loadRuntimeManifest(mirrorDir) : null;

function readPng(p) { return PNG.sync.read(fs.readFileSync(p)); }

let pages;
if (flags.all) pages = inv.pages;
else if (pageSel) {
  pages = inv.pages.filter(p => pageSel.includes(p.slug));
  const missing = pageSel.filter(s => !inv.pages.some(p => p.slug === s));
  if (missing.length) console.error(`  note: slugs not in inventory (skipped): ${missing.join(', ')}`);
} else {
  // one page per template cluster (diverse layouts), not the first N
  const sample = clusterSample(proj, inv.pages.map(p => p.slug), maxPages);
  const bySlug = new Map(inv.pages.map(p => [p.slug, p]));
  pages = sample.map(s => bySlug.get(s)).filter(Boolean);
}
if (!pages.length) { console.error('no pages selected'); process.exit(2); }
const results = [];
let mserver = null, mbase = null;
if (useMirror) { const s = await serveMirror(mirrorDir, runtimeManifest); mserver = s.srv; mbase = `http://127.0.0.1:${s.port}`; }
console.error(useMirror ? `  [mirror] rendering from local mirror (offline) at ${mbase}` : '  [live] no local mirror — rendering live source');
const browser = await chromium.launch({ headless: true });
for (const p of pages) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let rec = { slug: p.slug, url: p.url };
  // mirror files may carry the crawl host prefix (www.example.com_en_<slug>.html)
  const mirrorFile = fs.existsSync(`${mirrorDir}/${p.slug}.html`) ? `${p.slug}.html`
    : (fs.readdirSync(mirrorDir).find(f => f.endsWith(`_${p.slug}.html`)) || `${p.slug}.html`);
  const localMode = useMirror && fs.existsSync(`${mirrorDir}/${mirrorFile}`);
  // DOCTRINE: an offline gate never silently reaches for the network — a page
  // missing from an existing mirror is reported and excluded, not rendered live
  // (live WAF chrome scored as 'uncaptured content': the 73% Compose failure).
  if (useMirror && !localMode) {
    console.error(`  ~ ${p.slug}: not in local mirror — excluded (recapture via localize_site.py)`);
    results.push({ slug: p.slug, excluded: true, note: 'missing from local mirror' });
    await page.close().catch(() => {});
    continue;
  }
  try {
    if (localMode) {
      // offline: local server continues, manifest-captured runtime assets are
      // fulfilled from disk, everything else external is blocked
      await page.route('**/*', offlineRoute(mbase, mirrorDir, runtimeManifest, null));
    }
    await page.goto(localMode ? `${mbase}/${encodeURIComponent(mirrorFile)}` : p.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    try { await page.waitForLoadState('load', { timeout: 15000 }); } catch {}
    await page.waitForTimeout(4000);
    const src = `${outDir}/${p.slug}.source.png`;
    const rc = `${outDir}/${p.slug}.recon.png`;
    const df = `${outDir}/${p.slug}.diff.png`;
    await page.screenshot({ path: src, fullPage: true });
    const info = await page.evaluate(identify, sxaMode);
    await page.screenshot({ path: rc, fullPage: true });

    // Interactive reconstruction: the masked DOM (components visible, chrome hidden)
    // + a <base> so the site's OWN css/js/images load from origin — responsive and
    // hover menus work live. CSP <meta> is stripped so cross-origin assets aren't
    // blocked when served from localhost. Open via the orchestrator artifact route
    // or a static server (python3 -m http.server) in this dir.
    try {
      let html = await page.content();
      html = html.replace(/<meta[^>]+http-equiv=["']?content-security-policy["']?[^>]*>/gi, '');
      if (localMode) {
        // rendered from the mirror → asset refs are already local (assets/…); drop
        // any <base> and write into the mirror dir so they resolve offline.
        html = html.replace(/<base\b[^>]*>/gi, '');
        fs.writeFileSync(`${mirrorDir}/${p.slug}.recon.html`, html);
      } else {
        html = /<head[^>]*>/i.test(html)
          ? html.replace(/<head([^>]*)>/i, `<head$1><base href="${p.url}">`)
          : `<base href="${p.url}">` + html;
        fs.writeFileSync(`${outDir}/${p.slug}.recon.html`, html);
      }
    } catch { /* non-fatal: the screenshots + gate still stand */ }

    // component map: source screenshot + one hover-labelled overlay box per detected component
    try {
      fs.writeFileSync(`${outDir}/${p.slug}.overlay.html`,
        componentMapHtml(p.slug, info.boxes || [], info.docW || 1440, info.docH || 1));
    } catch { /* non-fatal */ }

    // pixel diff
    const a = readPng(src), b = readPng(rc);
    const w = Math.min(a.width, b.width), h = Math.min(a.height, b.height);
    const diff = new PNG({ width: w, height: h });
    // crop to common size if needed
    const crop = (img) => { if (img.width===w && img.height===h) return img; const o=new PNG({width:w,height:h}); PNG.bitblt(img,o,0,0,w,h,0,0); return o; };
    const ca = crop(a), cb = crop(b);
    const nDiff = pixelmatch(ca.data, cb.data, diff.data, w, h, { threshold: 0.1 });
    fs.writeFileSync(df, PNG.sync.write(diff));
    const total = w * h;
    const pixelSimilarity = +(100 * (1 - nDiff / total)).toFixed(2);
    rec = { ...rec, ok: true, nComps: info.nComps,
            contentCoverage: info.contentCoveragePct,       // GATE metric: real content captured (ignores cookie/a11y chrome)
            realOrphanChars: info.realOrphanChars,
            ignorableChars: info.ignorableChars,
            hiddenChars: info.hiddenChars,
            orphanSamples: info.orphanSamples,
            pixelSimilarity,                                // visual artifact: components-only vs source
            reconHtml: localMode ? `local-mirror/${p.slug}.recon.html` : `${p.slug}.recon.html`,
            mirrorPage: localMode ? `local-mirror/${p.slug}.html` : null,   // faithful local page (workflow-output-relative)
            overlayMap: `${p.slug}.overlay.html`,           // annotated component map
            local: localMode,
            dims: `${w}x${h}`,
            // SCRIPT-RENDERED pages (embeds — e.g. a Typeform body that is
            // only scripts): the visible text exists ONLY at runtime, so
            // content-coverage is meaningless; the bytes contract carries the
            // scripts and the page is judged on pixels alone (the authoritative
            // judge stays the ground-truth gate, live vs mirror, both with JS).
            pass: info.contentCoveragePct >= threshold
                  || (info.realOrphanChars < 300 && pixelSimilarity >= threshold) };
  } catch (e) {
    rec = { ...rec, ok: false, error: (e.message || String(e)).split('\\n')[0] };
  }
  results.push(rec);
  console.error(`  ${p.slug}: ${rec.ok ? rec.contentCoverage + '% content (' + rec.nComps + ' comps, pixelSim ' + rec.pixelSimilarity + '%)' : 'FAIL ' + rec.error}`);
  await page.close();
}
await browser.close();
if (mserver) mserver.close();

const pageSet = results.map(r => r.slug);
fs.writeFileSync(`${outDir}/reconstruct.json`, JSON.stringify(
  stampJson({ project: proj, threshold, pages: results }, 'reconstruct_probe.mjs', pageSet), null, 2));
writeSidecar(outDir, 'reconstruct_probe.mjs', pageSet);

// ── component map: source screenshot with a hover-labelled overlay per component ──
function componentMapHtml(slug, boxes, docW, docH) {
  const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  // paint big boxes first; smaller (more specific) boxes get a higher z-index so
  // hover always resolves to the innermost component.
  const sorted = boxes.slice().sort((a, b) => (b.w * b.h) - (a.w * a.h));
  const items = sorted.map((b, i) => {
    const type = roleType[b.role];
    const label = type || b.role;
    const sub = type ? b.role : b.tag;
    const pct = (n, d) => (100 * n / (d || 1)).toFixed(3) + '%';
    return `<div class="box${b.top ? ' top' : ''}" style="left:${pct(b.x, docW)};top:${pct(b.y, docH)};width:${pct(b.w, docW)};height:${pct(b.h, docH)};z-index:${10 + i}">`
      + `<span class="lbl"><b>${esc(label)}</b><em>${esc(sub)}</em></span></div>`;
  }).join('');
  return `<!doctype html><meta charset="utf8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Component map — ${esc(slug)}</title><style>
 body{margin:0;background:#0f1115;color:#e6e6e6;font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;z-index:99999;display:flex;gap:16px;align-items:center;padding:11px 18px;background:#171a21;border-bottom:1px solid #2a2f3a}
 header b{color:#fff} header .n{color:#9aa4b2}
 label{color:#cfd6e2;cursor:pointer;user-select:none} input{vertical-align:middle}
 .wrap{position:relative;width:100%;max-width:1440px;margin:0 auto}
 .wrap>img{width:100%;display:block}
 .box{position:absolute;box-sizing:border-box;border:1.5px solid rgba(0,119,191,.5);background:rgba(0,119,191,.04);transition:background .08s,border-color .08s}
 .box.top{border-color:rgba(0,119,191,.85)}
 .box:hover{background:rgba(214,33,125,.22);border-color:#d6217d;z-index:100000!important}
 .lbl{position:absolute;left:-1.5px;top:0;transform:translateY(-100%);display:flex;gap:8px;align-items:baseline;
      background:#d6217d;color:#fff;padding:2px 7px;border-radius:4px 4px 4px 0;white-space:nowrap;
      font:12px/1.5 ui-monospace,Menlo,monospace;opacity:0;pointer-events:none}
 .lbl em{color:#ffd0ea;font-style:normal;font-size:11px}
 .box:hover>.lbl{opacity:1}
 body.names .lbl{opacity:.92}
</style>
<header>
 <b>Component map</b><span class="n">${esc(slug)} · ${boxes.length} composants</span>
 <label style="margin-left:auto"><input type="checkbox" onchange="document.body.classList.toggle('names',this.checked)"> afficher tous les noms</label>
</header>
<div class="wrap"><img src="${esc(slug)}.source.png" alt="source">${items}</div>`;
}

// ── self-contained visual review page (open in a browser, no server needed) ──
function reviewHtml() {
  const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const card = r => {
    if (!r.ok) return `<section class="pg"><h2>${esc(r.slug)} — <span class="bad">FAILED</span> ${esc(r.error)}</h2></section>`;
    const badge = r.pass ? '<span class="ok">PASS</span>' : '<span class="warn">REVIEW</span>';
    const real = (r.orphanSamples || []).filter(o => !o.ignorable);
    const orphanHtml = real.length
      ? `<div class="orphans"><b>Real uncaptured content (${real.length}):</b><ul>${real.slice(0, 12).map(o => `<li><code>&lt;${esc(o.tag)} class="${esc(o.cls)}"&gt;</code> "${esc(o.text)}"</li>`).join('')}</ul></div>`
      : '<div class="orphans ok">✓ No real content uncaptured (only chrome/consent, which is expected).</div>';
    return `<section class="pg">
      <h2>${esc(r.slug)} ${badge}
        <small>content ${r.contentCoverage}% · pixelSim ${r.pixelSimilarity}% · ${r.nComps} components · <a href="${esc(r.url)}" target="_blank">source ↗</a>${r.mirrorPage ? ` · <a href="../${esc(r.mirrorPage)}" target="_blank">▶ page locale ↗</a>` : ''} · <a href="${esc(r.local ? '../' + r.reconHtml : (r.reconHtml || r.slug + '.recon.html'))}" target="_blank">▶ reconstruction${r.local ? ' (locale)' : ''} ↗</a> · <a href="${esc(r.slug)}.overlay.html" target="_blank">🗺 component map ↗</a></small></h2>
      <div class="viewer">
        <div class="slider" id="s_${esc(r.slug)}">
          <img class="recon" src="${esc(r.slug)}.recon.png" alt="reconstruction">
          <img class="source" src="${esc(r.slug)}.source.png" alt="source">
          <img class="diff" src="${esc(r.slug)}.diff.png" alt="diff" hidden>
          <div class="handle"></div>
          <input type="range" min="0" max="100" value="50" oninput="slide(this)">
        </div>
        <div class="ctrls">
          <button onclick="mode(this,'slider')" class="on">◧ Slider (drag)</button>
          <button onclick="mode(this,'source')">Source only</button>
          <button onclick="mode(this,'recon')">Reconstruction only</button>
          <button onclick="mode(this,'diff')">Diff heatmap</button>
        </div>
      </div>
      ${orphanHtml}
    </section>`;
  };
  const nOk = results.filter(r => r.ok && r.pass).length;
  return `<!doctype html><meta charset="utf8"><title>Reconstruction review — ${esc(proj)}</title>
<style>
 body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 header{padding:16px 24px;background:#171a21;position:sticky;top:0;border-bottom:1px solid #2a2f3a;z-index:9}
 h1{font-size:18px;margin:0} header small{color:#9aa4b2}
 .pg{padding:22px 24px;border-bottom:1px solid #20242e}
 h2{font-size:15px;margin:0 0 10px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
 h2 small{color:#9aa4b2;font-weight:400}
 a{color:#6cb6ff}
 .ok{color:#39d98a} .warn{color:#ffb454} .bad{color:#ff6b6b}
 .viewer{max-width:1024px}
 .slider{position:relative;border:1px solid #2a2f3a;background:#fff;overflow:hidden;user-select:none}
 .slider img{width:100%}
 .slider img:not([hidden]){display:block}
 .slider [hidden]{display:none!important}
 .slider .source,.slider .diff{position:absolute;top:0;left:0}
 .slider .handle{position:absolute;top:0;bottom:0;left:50%;width:2px;background:#ff00e5;pointer-events:none;box-shadow:0 0 6px #ff00e5}
 .slider input[type=range]{position:absolute;top:0;left:0;width:100%;height:100%;opacity:0;cursor:ew-resize;margin:0}
 .ctrls{margin:8px 0}
 .ctrls button{background:#20242e;color:#cfd6e2;border:1px solid #333a47;border-radius:6px;padding:5px 10px;margin-right:6px;cursor:pointer}
 .ctrls button.on{background:#2d6cdf;color:#fff;border-color:#2d6cdf}
 .orphans{margin-top:10px;font-size:13px;color:#cfd6e2} .orphans.ok{color:#39d98a}
 .orphans code{background:#20242e;padding:1px 5px;border-radius:4px;color:#ffd479}
 .legend{color:#9aa4b2;font-size:12px}
</style>
<header>
 <h1>Reconstruction fidelity review — ${esc(proj)} <span class="${nOk === results.length ? 'ok' : 'warn'}">(${nOk}/${results.length} pages pass)</span></h1>
 <small class="legend">Drag the slider to compare SOURCE (left) vs RECONSTRUCTION-from-extracted-components (right). Pink diff = pixels our components do NOT reproduce (section backgrounds / hero imagery / assets the template + import step supply). GATE = content coverage (all editable text captured).</small>
</header>
${results.map(card).join('\n')}
<script>
 function slide(inp){ const s=inp.closest('.slider'); const v=+inp.value;
   s.querySelector('.source').style.clipPath='inset(0 '+(100-v)+'% 0 0)';
   s.querySelector('.handle').style.left=v+'%'; }
 function mode(btn,m){ const v=btn.closest('.viewer'); v.querySelectorAll('.ctrls button').forEach(b=>b.classList.remove('on')); btn.classList.add('on');
   const s=v.querySelector('.slider'), src=s.querySelector('.source'), diff=s.querySelector('.diff'), rng=s.querySelector('input'), h=s.querySelector('.handle');
   diff.hidden=(m!=='diff'); rng.style.display=(m==='slider')?'block':'none'; h.style.display=(m==='slider')?'block':'none';
   if(m==='slider'){ src.hidden=false; src.style.clipPath='inset(0 '+(100-rng.value)+'% 0 0)'; }
   if(m==='source'){ src.hidden=false; src.style.clipPath='none'; }
   if(m==='recon'){ src.hidden=true; } }
 document.querySelectorAll('.slider input').forEach(slide);
</script>`;
}
fs.writeFileSync(`${outDir}/review.html`, reviewHtml());

console.log(`\n=== RECONSTRUCTION FIDELITY (from extracted components) — ${proj} ===`);
console.log(`GATE = content coverage (% of visible text inside a component; extraction-completeness).`);
console.log(`pixelSim = % of source pixels reproduced by components ALONE (the rest = section backgrounds /`);
console.log(`hero imagery / spacing the TEMPLATE + asset import must supply — see diff PNG).\n`);
let worstCov = 100, allPass = true;
for (const r of results) {
  if (r.excluded) { console.log(`  ${r.slug}: excluded (${r.note})`); continue; }
  if (!r.ok) { console.log(`  ${r.slug}: FAIL ${r.error}`); allPass = false; continue; }
  const flag = r.pass ? 'PASS' : 'BELOW THRESHOLD';
  console.log(`  ${r.slug.padEnd(30)} content=${r.contentCoverage}% (real-orphan ${r.realOrphanChars} chars, ignorable-chrome ${r.ignorableChars}) | pixelSim=${r.pixelSimilarity}% | ${r.nComps} comps  [${flag}]`);
  const realOrphans = (r.orphanSamples || []).filter(o => !o.ignorable).slice(0, 6);
  for (const o of realOrphans) console.log(`        ✗ REAL uncaptured content <${o.tag} class="${o.cls}">: "${o.text}"`);
  const ign = (r.orphanSamples || []).filter(o => o.ignorable).slice(0, 3);
  for (const o of ign) console.log(`        · ignorable chrome <${o.tag}>: "${o.text.slice(0, 45)}"`);
  worstCov = Math.min(worstCov, r.contentCoverage);
  if (!r.pass) allPass = false;
}
console.log(`\n  worst content coverage: ${worstCov}%  | threshold: ${threshold}%  | GATE: ${allPass ? 'GREEN — all content captured' : 'RED — orphan content exists; inspect diff PNGs'}`);
console.log(`\n  ▶ VISUAL REVIEW: open  ${outDir}/review.html  (slider source↔reconstruction + diff, per page)`);
console.log(`Output: ${outDir}/  (review.html + source/recon/diff PNGs + reconstruct.json)`);
process.exit(allPass ? 0 : 1);
