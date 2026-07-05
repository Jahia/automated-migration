// editor-surface.mjs — G6 reachability half (CONTRIBUTION-PLAN §9): every item
// child node must have a clickable EDIT FRAME in the Page Builder. A card whose
// markup is string-composed by its parent view has no frame — its (correct,
// editable) Content Editor form is UNREACHABLE through the editorial flow,
// which reads as "I can't edit this block" (observed live, careers grid).
//
// Prints JSON {modulePaths: [...]} of all [path]-marked modules in the frame.
// Usage: node editor-surface.mjs <host> <user> <pass> <site> <lang> <pagePath>
import { chromium } from "playwright";

const [host, user, pass, site, lang, page] = process.argv.slice(2);
const path = (page || "home").replace(/^\//, "").replace(/\.html$/, "");

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1500, height: 1000 } });
const p = await ctx.newPage();
let out = { modulePaths: [], error: null };
try {
  await p.goto(`${host}/cms/login`, { waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {});
  await p.fill('input[name="username"]', user).catch(() => {});
  await p.fill('input[name="password"]', pass).catch(() => {});
  await p.click('button[type="submit"], input[type="submit"]').catch(() => {});
  await p.waitForTimeout(2500);
  await p.goto(`${host}/jahia/jcontent/${site}/${lang}/pages/${path}`,
               { waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {});
  let fr = null;
  for (let i = 0; i < 12; i++) {
    await p.waitForTimeout(2500);
    fr = p.frames().find((f) => f.url().includes("editframe"));
    if (fr) break;
  }
  if (!fr) {
    out.error = "no editframe iframe (Page Builder did not load)";
  } else {
    out.modulePaths = await fr.evaluate(() =>
      Array.from(document.querySelectorAll("[path]"))
        .map((e) => e.getAttribute("path"))
        .filter(Boolean));
  }
} catch (e) {
  out.error = String(e).slice(0, 300);
} finally {
  await b.close();
}
console.log(JSON.stringify(out));
process.exit(out.error ? 1 : 0);
