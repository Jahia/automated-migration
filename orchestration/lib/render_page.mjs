// render_page.mjs — capture the POST-HYDRATION DOM of a page (P3 SPA support).
//
// The crawl's urllib fetch captures the raw HTTP response — the empty shell of
// any client-rendered site (content arrives by XHR after load). This renders
// the page in a real browser and captures what a VISITOR sees:
//   document.documentElement.outerHTML  after
//     network-idle + scroll-to-bottom (lazy/infinite) + MutationObserver quiescence.
//
// UNIFORM by design (no per-site / no "is this a SPA" branch): a server-rendered
// page's post-JS DOM ≈ its HTML (no-op), a SPA's content gets materialised. There
// is nothing site-specific to overfit.
//
// Determinism: we do NOT freeze the clock/rng DURING render — doing so breaks
// framework init (measured: freezing Date/requestAnimationFrame collapsed a real
// SPA render from 805 KB to 28 KB). Instead we let the page render faithfully and
// NORMALISE the captured output (strip volatile hydration attributes). Perfect
// byte-stability of a JS render is not achievable and not worth breaking the
// capture for; the mirror + ground-truth gates remain the objective judges.
//
// Usage: node render_page.mjs <url> <outHtmlPath> [--settle 1200] [--max 20000] [--timeout 45000]
import { chromium } from "playwright";
import fs from "fs";

const args = process.argv.slice(2);
const url = args[0];
const out = args[1];
const flag = (k, d) => {
  const i = args.indexOf("--" + k);
  return i >= 0 && args[i + 1] ? Number(args[i + 1]) : d;
};
if (!url || !out) {
  console.error("usage: render_page.mjs <url> <outHtmlPath> [--settle ms] [--max ms] [--timeout ms]");
  process.exit(2);
}
const SETTLE = flag("settle", 1200);   // quiet-window the MutationObserver must see
const MAXWAIT = flag("max", 20000);    // hard ceiling on post-load settling
const NAV_TIMEOUT = flag("timeout", 45000);

const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1,
  userAgent: UA });
const p = await ctx.newPage();
let ok = false;
let materialized = 0;
try {
  await p.goto(url, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
  try { await p.waitForLoadState("networkidle", { timeout: 15000 }); } catch { /* SPAs poll forever */ }

  // scroll the full height in steps to trigger lazy / viewport-gated content
  await p.evaluate(async () => {
    const step = Math.round(window.innerHeight * 0.9);
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 250));
    }
    window.scrollTo(0, 0);
  });

  // wait until the DOM stops mutating for SETTLE ms (or MAXWAIT ceiling) — the
  // generic "content has arrived" signal, no site-specific selector
  await p.evaluate(({ settle, max }) => new Promise((resolve) => {
    let last = performance.now();
    const obs = new MutationObserver(() => { last = performance.now(); });
    obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
    const t0 = performance.now();
    const tick = setInterval(() => {
      const now = performance.now();
      if (now - last >= settle || now - t0 >= max) { clearInterval(tick); obs.disconnect(); resolve(); }
    }, 100);
  }), { settle: SETTLE, max: MAXWAIT });

  // client-hydrated islands (Astro): their content lives ONLY in the props
  // attribute until the island renders — captured too early, the mirror ships
  // empty shells and the real content (carousels, collapsibles) silently
  // vanishes from every downstream artifact (business property carousel,
  // caught by inventory-coverage 2026-07-16). Wait bounded until every island
  // has element children; leftovers are captured as-is.
  try {
    await p.waitForFunction(
      () => [...document.querySelectorAll("astro-island")].every((i) => i.firstElementChild),
      null, { timeout: 12000 });
  } catch { /* unhydrated leftovers ship as-is — inventory-coverage will name them */ }

  // capture the materialised DOM, with an absolute <base> so the crawl's
  // relative-URL resolution (assets, links) still works against the source
  const html = await p.evaluate((pageUrl) => {
    // strip volatile attributes frameworks add on hydration (non-content, vary run-to-run)
    const VOLATILE = /^(data-reactroot|data-react-|data-v-|data-n-|data-hydrated|data-server-rendered|data-reactid|jsaction|data-emotion)/;
    document.querySelectorAll("*").forEach((el) => {
      for (const a of [...el.attributes]) {
        if (VOLATILE.test(a.name) || a.name.startsWith("data-reactid")) el.removeAttribute(a.name);
      }
    });
    if (!document.querySelector("base")) {
      const base = document.createElement("base");
      base.setAttribute("href", pageUrl);
      (document.head || document.documentElement).prepend(base);
    }
    return "<!doctype html>\n" + document.documentElement.outerHTML;
  }, url);

  materialized = html.length;
  fs.writeFileSync(out, html);
  ok = true;
} catch (e) {
  console.error("render_page: " + String(e).split("\n")[0]);
} finally {
  await b.close();
}
console.log(JSON.stringify({ ok, bytes: materialized, url }));
process.exit(ok ? 0 : 1);
