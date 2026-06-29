// edit-frame.mjs — assert shared regions render in the Page Builder edit frame.
// Invoked by edit-frame.sh. Logs in as root, opens the jcontent Page Builder for
// a page, finds the editframe iframe, and checks the shared regions actually
// render there — catching the failure where an AbsoluteArea (nav/footer/topbar)
// is BLANK in edit mode because its node has no child content nodes (works in
// live, invisible/uneditable in Page Builder).
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
      header: document.querySelectorAll(".header-navigation, header .navigation, #header").length,
      navItems: document.querySelectorAll("#main-nav li, nav li.level1, .header-navigation .level1").length,
      footer: document.querySelectorAll("#footer, .footerm2, footer .component").length,
      topbar: document.querySelectorAll(".top-navbar, .top-bar").length,
      // editable areas Jahia marks in edit mode
      editableAreas: document.querySelectorAll('[jahiatype="area"], [jahiatype="absoluteArea"], [type="area"], [path*="/main"]').length,
    }));
    findings.info = r;
    // shared regions present in the page tree must render in edit mode, not be blank
    if (r.header === 0) findings.fail.push("header/nav region is BLANK in the edit frame (AbsoluteArea with no children?)");
    if (r.footer === 0) findings.fail.push("footer region is BLANK in the edit frame (footer node has no child content?)");
    if (r.navItems === 0) findings.fail.push("navigation renders no items in the edit frame");
    if (r.editableAreas === 0) findings.fail.push("no editable area markers in the edit frame (content not editable in Page Builder)");
  }
} finally {
  await b.close();
}

console.log(JSON.stringify(findings, null, 1));
process.exit(findings.fail.length ? 1 : 0);
