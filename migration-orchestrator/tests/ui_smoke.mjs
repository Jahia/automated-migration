#!/usr/bin/env node
/**
 * ui_smoke.mjs — Playwright smoke tests for the orchestrator UI (/app).
 *
 * Julian's ask (2026-07-05): "quelques tests playwright pour tester les
 * différentes étapes, vérifie l'absence d'erreur javascript." Each view of the
 * run UI is navigated in a real browser; the test FAILS on ANY uncaught page
 * error or console.error — the class of bug that left the run UI blank
 * (ComponentModelView read m.templates.length with no templates in the manifest).
 *
 * Extension noise (chrome-extension:// injected scripts, web-capture-extension)
 * is filtered — those are the operator's browser, not the app.
 *
 * Usage: node migration-orchestrator/tests/ui_smoke.mjs [baseUrl] [runId]
 *   defaults: http://127.0.0.1:8011 , first run from /runs
 */
import { chromium } from "playwright";

const BASE = (process.argv[2] || "http://127.0.0.1:8011").replace(/\/$/, "");
let RUN = process.argv[3] || null;

const IGNORE = [
  /chrome-extension:\/\//i,
  /web-capture-extension/i,
  /injectlaunchmonitors/i,
  /favicon\.ico/i,
  /feature_flags/i,
  /Content Security Policy/i,
];
const ignored = (t) => IGNORE.some((re) => re.test(t || ""));

async function firstRun() {
  const r = await fetch(`${BASE}/runs`);
  const runs = await r.json();
  const list = Array.isArray(runs) ? runs : runs.runs || [];
  // prefer a paused/halted run (has a gate view to render), else the newest
  const paused = list.find((x) => ["paused", "halted"].includes(x.status));
  return (paused || list[0] || {}).run_id || null;
}

async function checkView(browser, name, path) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => { if (!ignored(e.message)) errors.push(`pageerror: ${e.message}`); });
  page.on("console", (m) => {
    if (m.type() === "error" && !ignored(m.text())) errors.push(`console.error: ${m.text()}`);
  });
  let nav = "ok";
  try {
    // NOT networkidle: the run page holds a persistent SSE stream (live log/status),
    // so the network never goes idle (same trap as jContent, migration rule 27).
    // domcontentloaded + poll the React root instead.
    await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page
      .waitForFunction(() => (document.querySelector("#root")?.childElementCount ?? 0) > 0, { timeout: 15000 })
      .catch(() => {});
    await page.waitForTimeout(1500); // let async artifact fetches settle (KpiBar etc.)
  } catch (e) {
    nav = `nav-failed: ${e.message}`;
  }
  // a crashed React tree leaves an empty #root — assert something rendered
  const rootChildren = await page.evaluate(
    () => document.querySelector("#root")?.childElementCount ?? -1,
  );
  await ctx.close();
  const ok = errors.length === 0 && nav === "ok" && rootChildren > 0;
  return { name, path, ok, errors, nav, rootChildren };
}

(async () => {
  if (!RUN) RUN = await firstRun();
  const views = [
    ["run list", "/app/"],
    ["run detail (gate)", `/app/runs/${RUN}`],
    ["schema", "/app/schema"],
  ];
  const browser = await chromium.launch();
  const results = [];
  for (const [name, path] of views) results.push(await checkView(browser, name, path));
  await browser.close();

  let failed = 0;
  for (const r of results) {
    console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name.padEnd(20)} ${r.path}  (root children: ${r.rootChildren})`);
    if (!r.ok) {
      failed++;
      if (r.nav !== "ok") console.log(`      ${r.nav}`);
      r.errors.slice(0, 6).forEach((e) => console.log(`      ${e}`));
    }
  }
  console.log(`\n${results.length - failed}/${results.length} views clean (run ${RUN})`);
  process.exit(failed ? 1 : 0);
})();
