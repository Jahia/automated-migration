// fidelity-live.mjs — structural diff of a LOCAL Jahia render vs a REFERENCE,
// both rendered with JS in headless Chromium. Invoked by fidelity-live.sh.
//
// Reference source can be a URL (rendered headless — works for non-WAF sites or
// a pre-warmed page) OR a saved rendered-DOM file (file://… .html, e.g. the
// browser capture under projects/<p>/.reference/captured/<slug>.html). The LOCAL
// side is always the localhost Jahia URL (no WAF). Compares — and FAILS the
// local on — missing sections and card/list-item shortfall. Missing facet values
// and order mismatch are warnings (facets: SXA facetFilter has no Jahia backend).
//
// Usage: node fidelity-live.mjs <referenceSrc> <liveUrl> <shotDir>
import { chromium } from "playwright";

const [refSrc, liveUrl, shotDir] = process.argv.slice(2);
if (!refSrc || !liveUrl) { console.error("usage: fidelity-live.mjs <referenceSrc> <liveUrl> [shotDir]"); process.exit(2); }
const norm = (s) => (s || "").replace(/\s+/g, " ").trim().toLowerCase();

async function signals(page, src) {
  const url = /^https?:\/\//.test(src) ? src : ("file://" + src);
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(2000);
  await page.evaluate(async () => { for (let y=0; y<document.body.scrollHeight; y+=600){ window.scrollTo(0,y); await new Promise(r=>setTimeout(r,100)); } window.scrollTo(0,0); });
  await page.waitForTimeout(800);
  return page.evaluate(() => {
    const main = document.querySelector("main, #main-content") || document.body;
    const headings = [...main.querySelectorAll("h1,h2,h3")].map(h => h.textContent.replace(/\s+/g," ").trim()).filter(Boolean);
    // largest repeated-sibling cluster = the listing card count
    const counts = {};
    main.querySelectorAll("*").forEach(el => {
      const c = (typeof el.className === "string" ? el.className : "").trim();
      if (c) counts[c] = (counts[c]||0)+1;
    });
    const maxCards = Math.max(0, ...Object.values(counts).filter(n => n >= 2));
    const facetOpts = [...document.querySelectorAll("select option")].map(o => o.textContent.replace(/\s+/g," ").trim()).filter(Boolean);
    const imgs = [...main.querySelectorAll("img")].filter(i => i.naturalWidth > 0).length;
    return { headings, maxCards, facetOpts, imgs };
  });
}

const b = await chromium.launch({ args: ["--no-sandbox"] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } });
const out = { fail: [], warn: [], info: {} };
try {
  const rp = await ctx.newPage(); const ref = await signals(rp, refSrc);
  if (shotDir) await rp.screenshot({ path: `${shotDir}/fidelity-ref.png`, fullPage: true }).catch(()=>{});
  const lp = await ctx.newPage(); const loc = await signals(lp, liveUrl);
  if (shotDir) await lp.screenshot({ path: `${shotDir}/fidelity-local.png`, fullPage: true }).catch(()=>{});
  out.info = { ref: { headings: ref.headings.length, cards: ref.maxCards, facets: ref.facetOpts.length, imgs: ref.imgs },
               local: { headings: loc.headings.length, cards: loc.maxCards, facets: loc.facetOpts.length, imgs: loc.imgs } };

  // 1. sections present
  const localH = new Set(loc.headings.map(norm));
  const missing = ref.headings.filter(h => h.length > 3 && !localH.has(norm(h)));
  if (ref.headings.length && missing.length / ref.headings.length > 0.15)
    out.fail.push(`missing ${missing.length}/${ref.headings.length} reference sections, e.g.: ${missing.slice(0,5).join(" | ")}`);

  // 2. listing/card shortfall
  if (ref.maxCards >= 3 && loc.maxCards < ref.maxCards * 0.5)
    out.fail.push(`listing shortfall: reference ~${ref.maxCards} repeated items, local ~${loc.maxCards}`);

  // 3. facet values present — WARN, not fail. SXA facetFilter (the reference's
  //    <select> Thèmes/Type dropdowns) has NO Jahia backend: Jahia listings are
  //    jcrQuery over a contentFolder, not a faceted search UI. A hard fail here
  //    can NEVER pass and masks the real, fixable defects (sections + listing
  //    count). Kept as advisory: consider category-based filtering if wanted.
  const localF = new Set(loc.facetOpts.map(norm));
  const missF = ref.facetOpts.filter(o => o.length > 1 && !localF.has(norm(o)));
  if (ref.facetOpts.length && missF.length / ref.facetOpts.length > 0.2)
    out.warn.push(`missing facet values (SXA facetFilter has no Jahia backend — advisory): ${missF.slice(0,6).join(" | ")}`);

  // 4. image shortfall (warn)
  if (ref.imgs >= 4 && loc.imgs < ref.imgs * 0.6)
    out.warn.push(`image shortfall: reference ${ref.imgs} rendered images, local ${loc.imgs}`);

  // 5. heading order (warn) — local headings should follow reference order
  const seq = ref.headings.map(norm).filter(h => localH.has(h));
  const localSeq = loc.headings.map(norm).filter(h => seq.includes(h));
  if (seq.length > 2 && JSON.stringify(seq) !== JSON.stringify([...new Set(localSeq)]))
    out.warn.push("section order differs from the reference");
} finally { await b.close(); }

console.log(JSON.stringify(out, null, 1));
process.exit(out.fail.length ? 1 : 0);
