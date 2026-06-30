// edit-frame.mjs — assert the Page Builder edit frame LOADS and the page is
// editable, and REPORT (warn) on shared-region rendering.
//
// Ground truth on jmix:hiddenType + AbsoluteArea (so this probe is not misread):
//   • jmix:hiddenType on a singleton layout type (nav/footer/topbar) hides it from
//     the Page Builder content PICKER and blocks INLINE selection — it does NOT
//     stop the view from rendering. The view renders in LIVE always.
//   • An AbsoluteArea region appears populated in the EDIT frame once its node has
//     child content (the "AbsoluteArea-needs-children" rule); empty = blank in edit
//     but fine in live. So a blank shared region in edit is NOT a defect — it is
//     either not-yet-populated content or an intentionally non-inline-editable region.
// Therefore this probe FAILS only when Page Builder didn't load or the page has NO
// editable area markers. Blank nav/footer = INFO/warn, never a hard fail.
//
// Usage: node edit-frame.mjs <host> <user> <pass> <site> <lang> <pagePath>
import { chromium } from "playwright";

const [host, user, pass, site, lang, page] = process.argv.slice(2);
if (!host || !site) {
  console.error("usage: edit-frame.mjs <host> <user> <pass> <site> <lang> <pagePath>");
  process.exit(2);
}
const path = (page || "home").replace(/^\//, "").replace(/\.html$/, "");

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1500, height: 1000 } });
const p = await ctx.newPage();
const findings = { fail: [], info: {} };
try {
  await p.goto(`${host}/cms/login`, { waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {});
  await p.fill('input[name="username"]', user).catch(() => {});
  await p.fill('input[name="password"]', pass).catch(() => {});
  await p.click('button[type="submit"], input[type="submit"]').catch(() => {});
  await p.waitForTimeout(2500);

  await p.goto(`${host}/jahia/jcontent/${site}/${lang}/pages/${path}`, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
  await p.waitForTimeout(7000);

  const fr = p.frames().find((f) => f.url().includes("editframe"));
  if (!fr) {
    findings.fail.push("no editframe iframe found (Page Builder did not load)");
  } else {
    const r = await fr.evaluate(() => ({
      // broad: match generic rendered markup AND the AbsoluteArea node path, so a
      // populated nav/footer is detected regardless of the module's CSS class names.
      header: document.querySelectorAll(".header-navigation, header, #header, nav.navbar, [path$='/nav'], [path*='/nav/']").length,
      navItems: document.querySelectorAll("#main-nav li, nav li.level1, .header-navigation .level1, .navbar li").length,
      footer: document.querySelectorAll("#footer, .footerm2, footer, .footer, .component.footer, [path$='/footer'], [path*='/footer/']").length,
      topbar: document.querySelectorAll(".top-navbar, .top-bar, [path$='/topbar']").length,
      // editable areas Jahia marks in edit mode
      editableAreas: document.querySelectorAll('[jahiatype="area"], [jahiatype="absoluteArea"], [type="area"], [path*="/main"]').length,
    }));
    findings.info = r;
    // Blank shared region in edit = WARN, never a hard fail (see ground-truth header):
    // jmix:hiddenType renders in live; in edit it shows once the AbsoluteArea has
    // child content. The real gate is that Page Builder loaded with editable areas.
    if (r.header === 0) findings.info._headerBlank = "nav region blank in edit — populate it (AbsoluteArea-needs-children); it renders in live regardless";
    if (r.footer === 0) findings.info._footerBlank = "footer region blank in edit — populate it (AbsoluteArea-needs-children); it renders in live regardless";
    if (r.editableAreas === 0) findings.fail.push("no editable area markers in the edit frame (content not editable in Page Builder)");
  }
} finally {
  await b.close();
}

console.log(JSON.stringify(findings, null, 1));
process.exit(findings.fail.length ? 1 : 0);
