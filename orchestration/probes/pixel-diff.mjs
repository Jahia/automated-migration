// pixel-diff.mjs — PIXEL-PARITY diff of a LOCAL Jahia render vs a REFERENCE,
// both rendered with JS in headless Chromium at the same viewport.
//
// The pixel-level companion to fidelity-live.mjs (structural). Renders both
// sides full-page, normalizes the dynamic noise (freezes CSS animations and
// JS timers, hides configured overlay selectors like consent banners), then
// compares the two screenshots pixel-by-pixel INSIDE the browser via canvas —
// zero native/npm image dependencies. Writes ref.png / local.png / diff.png
// (differing pixels in red over a faded reference) so a human or agent can SEE
// exactly what is off, and fails when the differing-pixel ratio exceeds the
// threshold.
//
// Per-channel tolerance absorbs anti-aliasing; the threshold is the honest
// dial: 0 is unattainable on JS-rendered sites, so "pixel perfect" is enforced
// as diff% <= maxDiffPct (default 2.0, override per call or per project via
// pixel.sh's config).
//
// A file:// reference renders NAKED (its same-origin asset paths resolve to
// nothing), which makes a pixel diff meaningless. So when referenceOrigin is
// given and the reference is a file, the DOM gets an injected <base href> and
// the context sends real browser headers (UA + Referer) — capture-time DOM,
// live-origin CSS/images (static assets pass WAFs that block full page loads).
//
// Efficiency features:
//   * REFERENCE RENDER CACHE — between pixel iterations only the LOCAL side
//     changes; the reference render (30-60s) is reused from outDir when the
//     cache key (source file mtime/size + hide + origin) is unchanged.
//   * CALIBRATE MODE — pass "--calibrate" as <liveUrl>: renders the REFERENCE
//     TWICE and diffs the two renders. The result is the NOISE FLOOR (fonts,
//     AA, timing) — the empirically achievable minimum, used to auto-set a
//     fair threshold before any agent burns attempts on an unpassable gate.
//
// Usage: node pixel-diff.mjs <referenceSrc> <liveUrl|--calibrate> <outDir> [maxDiffPct] [hideSelectorsCSV] [referenceOrigin]
import { chromium } from "playwright";
import { mkdirSync, writeFileSync, readFileSync, existsSync, statSync } from "fs";
import { resolve } from "path";

const [refSrcArg, liveUrl, outDir, maxArg, hideCsv, refOrigin] = process.argv.slice(2);
if (!refSrcArg || !liveUrl || !outDir) {
  console.error("usage: pixel-diff.mjs <referenceSrc> <liveUrl|--calibrate> <outDir> [maxDiffPct] [hideSelectorsCSV] [referenceOrigin]");
  process.exit(2);
}
const CALIBRATE = liveUrl === "--calibrate";
const MAX_DIFF_PCT = parseFloat(maxArg || "2.0");
const HIDE = (hideCsv || "").split("|").map((s) => s.trim()).filter(Boolean);
const CHANNEL_TOL = 24; // per-channel tolerance (anti-aliasing / font hinting)

mkdirSync(outDir, { recursive: true });

// reference cache key: source identity + everything that affects its render
const refIsUrl = /^https?:\/\//.test(refSrcArg);
const refStat = refIsUrl ? null : statSync(resolve(refSrcArg));
const CACHE_KEY = JSON.stringify({
  src: refIsUrl ? refSrcArg : resolve(refSrcArg),
  mtime: refStat ? refStat.mtimeMs : null, size: refStat ? refStat.size : null,
  hide: HIDE, origin: refOrigin || null, vp: "1440x1000", tol: CHANNEL_TOL, v: 2,
});
const refCacheValid =
  !CALIBRATE &&
  existsSync(`${outDir}/.refkey`) && existsSync(`${outDir}/ref.png`) && existsSync(`${outDir}/refmarks.json`) &&
  readFileSync(`${outDir}/.refkey`, "utf-8") === CACHE_KEY;

// file reference + origin -> inject <base> so capture-time DOM loads its real assets.
// Paths MUST be absolute: file:// + a relative path is an invalid URL that fails
// silently into about:blank (a pure-white "reference").
let refSrc = /^https?:\/\//.test(refSrcArg) ? refSrcArg : resolve(refSrcArg);
if (refOrigin && !/^https?:\/\//.test(refSrcArg)) {
  const html = readFileSync(refSrc, "utf-8")
    .replace(/<head([^>]*)>/i, `<head$1><base href="${refOrigin.replace(/\/$/, "")}/">`);
  refSrc = resolve(outDir, "_ref-based.html");
  writeFileSync(refSrc, html);
}

async function renderShot(page, src) {
  const url = /^https?:\/\//.test(src) ? src : "file://" + src;
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(2000);
  // trigger lazy content / scroll reveals, then return to top
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 600) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 100));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(800);
  // freeze animations/transitions + stop JS-driven movement (carousels, tickers),
  // and FORCE-REVEAL scroll-reveal content: imported themes hide sections at
  // opacity:0 until site JS adds a reveal class on scroll — that JS may not run
  // on a file:// reference, leaving a blank page. Normalize BOTH sides.
  await page.addStyleTag({
    content:
      "*,*::before,*::after{animation:none!important;transition:none!important;" +
      "scroll-behavior:auto!important;caret-color:transparent!important}" +
      "body *{opacity:1!important;visibility:visible!important}" +
      "[class*=reveal],[class*=slide-],[class*=fade],[data-aos]{transform:none!important}",
  }).catch(() => {});
  await page.evaluate(() => {
    // clear every pending timer — generic, source-agnostic way to stop autoplay
    const top = setTimeout(() => {}, 0);
    for (let i = 0; i <= top; i++) { clearTimeout(i); clearInterval(i); }
  }).catch(() => {});
  if (HIDE.length) {
    await page.addStyleTag({
      content: HIDE.map((s) => `${s}{display:none!important;visibility:hidden!important}`).join("\n"),
    }).catch(() => {});
  }
  await page.waitForTimeout(300);
  // NOTE: no `animations:"disabled"` here — Playwright CANCELS animations, which
  // resets fill-mode:forwards reveal animations to their hidden initial state
  // (blank page). The injected freeze CSS + force-reveal above handle stillness.
  return page.screenshot({ fullPage: true });
}

// DOM landmarks with absolute y positions — the translation layer that turns
// pixel bands into language a TEXT model can act on ("y 600-900: ref has
// h2 'La Grande Expo' + a.cta, local has p raw text").
async function landmarks(page) {
  return page.evaluate(() => {
    const out = [];
    const sel = "h1,h2,h3,h4,section,header,footer,nav,main>div,main>*>div,img,iframe,video,button,a[class*=btn],a[class*=cta]";
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect();
      const y = r.top + window.scrollY;
      if (r.width < 40 || r.height < 16) continue;
      if (r.height > 1500) continue; // page-spanning wrapper — crowds out real landmarks
      let desc;
      const tag = el.tagName.toLowerCase();
      if (/^h[1-4]$/.test(tag)) desc = `${tag} "${(el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60)}"`;
      else if (tag === "img") desc = `img ${(el.currentSrc || el.src || "").split("/").pop().split("?")[0].slice(0, 40)} (${r.width | 0}x${r.height | 0})`;
      else if (tag === "iframe" || tag === "video") desc = `${tag} (${r.width | 0}x${r.height | 0})`;
      else {
        const cls = (typeof el.className === "string" ? el.className : "").split(/\s+/).filter(Boolean).slice(0, 2).join(".");
        const txt = (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40);
        desc = `${tag}${cls ? "." + cls : ""}${txt ? ` "${txt}"` : ""}`;
      }
      out.push({ y: Math.round(y), h: Math.round(r.height), desc });
      if (out.length >= 300) break;
    }
    return out;
  });
}

const b = await chromium.launch({ args: ["--no-sandbox"] });
const ctx = await b.newContext({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
  // real browser identity: the reference origin's CDN serves static assets to a
  // browser-looking request (same trick as the server-side image proxy)
  userAgent:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  ...(refOrigin ? { extraHTTPHeaders: { Referer: refOrigin.replace(/\/$/, "") + "/" } } : {}),
});
let out;
try {
  let refBuf, refMarks;
  if (refCacheValid) {
    refBuf = readFileSync(`${outDir}/ref.png`);
    refMarks = JSON.parse(readFileSync(`${outDir}/refmarks.json`, "utf-8"));
  } else {
    const rp = await ctx.newPage();
    refBuf = await renderShot(rp, refSrc);
    refMarks = await landmarks(rp);
    writeFileSync(`${outDir}/ref.png`, refBuf);
    writeFileSync(`${outDir}/refmarks.json`, JSON.stringify(refMarks));
    writeFileSync(`${outDir}/.refkey`, CACHE_KEY);
  }
  const lp = await ctx.newPage();
  // calibrate: the "local" side is a SECOND fresh render of the reference
  const locBuf = await renderShot(lp, CALIBRATE ? refSrc : liveUrl);
  const locMarks = await landmarks(lp);
  writeFileSync(`${outDir}/local.png`, locBuf);

  // pixel comparison inside Chromium via canvas — no image libs needed
  const cp = await ctx.newPage();
  out = await cp.evaluate(
    async ({ refB64, locB64, tol }) => {
      const load = (b64) =>
        new Promise((res, rej) => {
          const im = new Image();
          im.onload = () => res(im);
          im.onerror = rej;
          im.src = "data:image/png;base64," + b64;
        });
      const [ri, li] = await Promise.all([load(refB64), load(locB64)]);
      const W = Math.max(ri.width, li.width);
      const H = Math.max(ri.height, li.height);
      const draw = (im) => {
        const c = document.createElement("canvas");
        c.width = W; c.height = H;
        const g = c.getContext("2d", { willReadFrequently: true });
        g.fillStyle = "#ffffff"; g.fillRect(0, 0, W, H);
        g.drawImage(im, 0, 0);
        return g.getImageData(0, 0, W, H).data;
      };
      const rd = draw(ri), ld = draw(li);
      const dc = document.createElement("canvas");
      dc.width = W; dc.height = H;
      const dg = dc.getContext("2d");
      const di = dg.createImageData(W, H);
      const dd = di.data;
      const BAND = 250; // px — per-band diff for the DOM-anchored region report
      const bands = new Array(Math.ceil(H / BAND)).fill(0);
      let diff = 0;
      for (let i = 0; i < rd.length; i += 4) {
        const d =
          Math.abs(rd[i] - ld[i]) > tol ||
          Math.abs(rd[i + 1] - ld[i + 1]) > tol ||
          Math.abs(rd[i + 2] - ld[i + 2]) > tol;
        if (d) {
          diff++;
          bands[((i / 4 / W) | 0) / BAND | 0]++;
          dd[i] = 255; dd[i + 1] = 0; dd[i + 2] = 0; dd[i + 3] = 255;
        } else {
          // faded grayscale of the reference for context
          const g = (rd[i] * 0.3 + rd[i + 1] * 0.59 + rd[i + 2] * 0.11) | 0;
          dd[i] = g; dd[i + 1] = g; dd[i + 2] = g; dd[i + 3] = 60;
        }
      }
      dg.putImageData(di, 0, 0);
      return {
        width: W, height: H,
        refSize: [ri.width, ri.height], localSize: [li.width, li.height],
        totalPx: W * H, diffPx: diff,
        diffPct: +((100 * diff) / (W * H)).toFixed(3),
        bandPx: BAND,
        bandDiffPct: bands.map((n, k) => +((100 * n) / (W * Math.min(BAND, H - k * BAND))).toFixed(1)),
        diffPngB64: dc.toDataURL("image/png").split(",")[1],
      };
    },
    { refB64: refBuf.toString("base64"), locB64: locBuf.toString("base64"), tol: CHANNEL_TOL },
  );
  writeFileSync(`${outDir}/diff.png`, Buffer.from(out.diffPngB64, "base64"));
  delete out.diffPngB64;

  // ── DOM-anchored region report: pixels translated into actionable language ──
  const inBand = (marks, y0, y1) => {
    // prefer landmarks that START in the band; pad with overlapping ones
    const starts = marks.filter((m) => m.y >= y0 && m.y < y1);
    const overlaps = marks.filter((m) => m.y < y0 && m.y + m.h > y0);
    return [...starts, ...overlaps].slice(0, 6).map((m) => `y${m.y} ${m.desc}`);
  };
  const hot = out.bandDiffPct
    .map((pct, k) => ({ y0: k * out.bandPx, y1: Math.min((k + 1) * out.bandPx, out.height), pct }))
    .filter((band) => band.pct > 10)
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 12)
    .map((band) => ({
      ...band,
      reference: inBand(refMarks, band.y0, band.y1),
      local: inBand(locMarks, band.y0, band.y1),
    }))
    .sort((a, b) => a.y0 - b.y0);
  const heightGapPx = out.refSize[1] - out.localSize[1];
  const report = {
    diffPct: out.diffPct, maxDiffPct: MAX_DIFF_PCT,
    refHeight: out.refSize[1], localHeight: out.localSize[1],
    heightGapPx,
    heightHint:
      heightGapPx > 200 ? `LOCAL page is ${heightGapPx}px SHORTER than the reference — content is missing`
      : heightGapPx < -200 ? `LOCAL page is ${-heightGapPx}px TALLER than the reference — extra/duplicated content`
      : "heights roughly match",
    hotRegions: hot,
    artifacts: { ref: `${outDir}/ref.png`, local: `${outDir}/local.png`, diff: `${outDir}/diff.png` },
  };
  writeFileSync(`${outDir}/report.json`, JSON.stringify(report, null, 1));
  out.report = `${outDir}/report.json`;
} finally {
  await b.close();
}

out.maxDiffPct = MAX_DIFF_PCT;
out.pass = CALIBRATE ? true : out.diffPct <= MAX_DIFF_PCT;
out.calibrate = CALIBRATE;
out.refCacheHit = refCacheValid;
out.artifacts = { ref: `${outDir}/ref.png`, local: `${outDir}/local.png`, diff: `${outDir}/diff.png` };
delete out.bandDiffPct;
console.log(JSON.stringify(out, null, 1));
process.exit(out.pass ? 0 : 1);
