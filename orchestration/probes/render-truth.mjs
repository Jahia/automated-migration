// render-truth.mjs — observable render checks via headless Chromium.
// Invoked by render-truth.sh (which resolves Playwright + passes args).
//
// Loads a page, scrolls through it (to trigger lazy-load + scroll-reveal), then
// asserts the defects that slipped past count/grep-based verification:
//   - broken images (naturalWidth == 0) in the main content
//   - content stuck hidden (opacity ~0 / 0-height) after a full scroll
//   - collapsed shared regions (header/nav/footer present but ~0 height)
//   - video sections with no <iframe>/<video> player
//   - (warning) dark-on-dark / low-contrast text in key regions
// Writes a screenshot artifact and prints a JSON summary. Exit 1 on any FAIL.
//
// Usage: node render-truth.mjs <url> <screenshotPath> [--edit]
import { chromium } from "playwright";

const url = process.argv[2];
const shot = process.argv[3];
const editMode = process.argv.includes("--edit");
if (!url) {
  console.error("usage: render-truth.mjs <url> <screenshotPath> [--edit]");
  process.exit(2);
}

const lum = (rgb) => {
  const m = (rgb || "").match(/\d+(\.\d+)?/g);
  if (!m) return null;
  const [r, g, b] = m.map(Number).map((v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ctx.newPage();

const findings = { fail: [], warn: [], info: {} };
try {
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(2500);
  // scroll through to trigger lazy-load + IntersectionObserver reveals
  await page.evaluate(async () => {
    const h = document.body.scrollHeight;
    for (let y = 0; y < h; y += 500) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 130));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(1500);

  const r = await page.evaluate(() => {
    const inMain = (el) => el.closest("main, #main-content, .footerm2, #footer, header") || document.body.contains(el);
    const SKIP = (el) =>
      el.closest('[aria-hidden="true"], template, noscript, .sr-only, .visually-hidden, [hidden], script, style');
    const cs = (el) => getComputedStyle(el);
    const box = (el) => el.getBoundingClientRect();

    // 1. broken images in content
    const brokenImages = [...document.querySelectorAll("main img, #main-content img, footer img, header img")]
      .filter((i) => !SKIP(i) && (i.naturalWidth === 0 || !i.complete))
      .map((i) => (i.currentSrc || i.src || "").split("/").pop().split("?")[0])
      .slice(0, 20);

    // 2. content stuck hidden after full scroll (reveal failed)
    const hidden = [];
    for (const el of document.querySelectorAll("main *, #main-content *, .footerm2 *")) {
      if (SKIP(el)) continue;
      const hasImg = el.tagName === "IMG" || el.querySelector(":scope > img");
      const txt = (el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 40));
      if (!hasImg && !txt) continue;
      const c = cs(el);
      const rect = box(el);
      if (rect.width < 2) continue;
      const op = parseFloat(c.opacity);
      if (op < 0.1 || c.visibility === "hidden") {
        hidden.push((el.className && String(el.className).slice(0, 40)) || el.tagName);
        if (hidden.length > 15) break;
      }
    }

    // 3. collapsed shared regions
    const collapsed = [];
    for (const sel of ["header", "nav#main-nav", "#footer", ".footerm2"]) {
      const el = document.querySelector(sel);
      if (el && el.children.length > 0 && box(el).height < 5) collapsed.push(sel);
    }

    // 4. video section without a WORKING player. A bare <iframe> is fine. A
    //    <video> only counts if it has a playable source — `type="video/youtube"`
    //    (or vimeo) on a native <video> never plays, which was the real bug.
    const videoNoPlayer = [...document.querySelectorAll(".sxa-video-wrapper, .component.video")]
      .filter((v) => {
        if (box(v).height < 10) return false;
        if (v.querySelector("iframe")) return false;
        const vid = v.querySelector("video");
        if (!vid) return true;
        const srcs = [...vid.querySelectorAll("source")];
        const playable = (vid.src && vid.src.length > 0) ||
          srcs.some((s) => !/youtube|vimeo/i.test(s.type || "") && (s.src || "").length > 0);
        return !playable;
      })
      .map((v) => String(v.className).slice(0, 40))
      .slice(0, 5);

    // 5. low-contrast text (warning) on key regions
    const lowContrast = [];
    for (const el of document.querySelectorAll("header a, .search-result-item .field-title, .top-navbar a")) {
      if (SKIP(el) || !el.textContent.trim()) continue;
      let bg = "rgba(0, 0, 0, 0)", n = el;
      while (n && /, 0\)$/.test(bg)) { bg = cs(n).backgroundColor; n = n.parentElement; }
      // only assess contrast when we resolved a solid (non-transparent) background
      if (/, 0\)$/.test(bg)) continue;
      lowContrast.push({ fg: cs(el).color, bg, t: el.textContent.trim().slice(0, 24) });
    }

    return {
      brokenImages,
      hidden,
      collapsed,
      videoNoPlayer,
      lowContrast: lowContrast.slice(0, 12),
      imgTotal: document.querySelectorAll("main img, footer img, header img").length,
    };
  });

  findings.info = { imgTotal: r.imgTotal };
  if (r.brokenImages.length) findings.fail.push(`broken images (naturalWidth=0): ${r.brokenImages.join(", ")}`);
  if (r.hidden.length) findings.fail.push(`content stuck hidden (opacity~0 after scroll): ${r.hidden.join(", ")}`);
  if (r.collapsed.length) findings.fail.push(`collapsed regions (0 height with children): ${r.collapsed.join(", ")}`);
  if (r.videoNoPlayer.length) findings.fail.push(`video section without <iframe>/<video>: ${r.videoNoPlayer.join(", ")}`);

  // contrast warnings
  for (const c of r.lowContrast) {
    const lf = lum(c.fg), lb = lum(c.bg);
    if (lf == null || lb == null) continue;
    const ratio = (Math.max(lf, lb) + 0.05) / (Math.min(lf, lb) + 0.05);
    if (ratio < 2.0) findings.warn.push(`low contrast (${ratio.toFixed(1)}:1) "${c.t}" fg=${c.fg} bg=${c.bg}`);
  }

  if (shot) await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
} finally {
  await b.close();
}

console.log(JSON.stringify(findings, null, 1));
process.exit(findings.fail.length ? 1 : 0);
