#!/usr/bin/env node
/**
 * freeze_page.mjs — bake a JS-revealed SPA page into a JS-off-faithful static DOM.
 *
 * WHY: the overlay strips the page's client scripts (so the SPA can't re-hydrate and wipe
 * the injected zone boundaries — Julian: "le zonage disparait au bout de 0.5s"). But a SPA
 * whose CONTENT VISIBILITY is JS-driven (discoverasr: hero/nav/images start display:none,
 * revealed on load + scroll) then renders blank once the scripts are gone. Freezing runs the
 * site JS ONCE (load + scroll to trigger every reveal), waits for the DOM to settle, and
 * captures document.documentElement.outerHTML — the fully-revealed state. Re-rendered with
 * NO JS, that capture is faithful (proven on discoverasr en). zone_to_contentload
 * --overlay --overlay-src frozen then annotates the frozen DOM, so the overlay renders
 * faithfully AND keeps the interactive popin (our own script), touching nothing else.
 *
 * Generic — no per-site logic (anti-overfit): serve mirror, load, scroll, settle, capture.
 *
 * Usage: node orchestration/lib/freeze_page.mjs <project> [--pages a,b] [--port 8971]
 */
import { chromium } from 'playwright';
import http from 'http';
import { readFileSync, existsSync, readdirSync, writeFileSync, statSync } from 'fs';
import path from 'path';

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..');
const args = process.argv.slice(2);
const project = args[0];
if (!project || project.startsWith('--')) { console.error('usage: freeze_page.mjs <project> [--pages a,b] [--port N]'); process.exit(2); }
const only = args.includes('--pages') ? args[args.indexOf('--pages') + 1].split(',') : null;
const port = args.includes('--port') ? Number(args[args.indexOf('--port') + 1]) : 8971;
const MIR = path.join(REPO, 'projects', project, 'workflow-output', 'local-mirror');
if (!existsSync(MIR)) { console.error('no mirror:', MIR); process.exit(2); }

const MIME = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
  '.gif': 'image/gif', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
  '.avif': 'image/avif', '.ico': 'image/x-icon' };

const srv = http.createServer((req, res) => {
  try {
    let p = decodeURIComponent(req.url.split('?')[0]);
    let fp = path.join(MIR, p);
    if (!fp.startsWith(MIR)) { res.writeHead(403); return res.end(); }
    if (existsSync(fp) && statSync(fp).isFile()) {
      res.writeHead(200, { 'Content-Type': MIME[path.extname(fp).toLowerCase()] || 'application/octet-stream' });
      return res.end(readFileSync(fp));
    }
    res.writeHead(404); res.end();
  } catch (e) { res.writeHead(500); res.end(); }
});
await new Promise(r => srv.listen(port, '127.0.0.1', r));

const slugs = (only || readdirSync(MIR)
  .filter(f => f.endsWith('.html') && !f.endsWith('.overlay.html') && !f.endsWith('.frozen.html'))
  .map(f => f.replace(/\.html$/, ''))).sort();

const b = await chromium.launch();
let ok = 0, fail = 0;
for (const slug of slugs) {
  try {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 1000 } });
    const pg = await ctx.newPage();
    await pg.goto(`http://127.0.0.1:${port}/${slug}.html`, { waitUntil: 'load', timeout: 30000 }).catch(() => {});
    await pg.waitForTimeout(2200);
    // scroll the whole page to trip lazy/scroll-reveal, then settle
    await pg.evaluate(async () => {
      const H = document.body.scrollHeight;
      for (let y = 0; y < H; y += 700) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); }
      window.scrollTo(0, 0);
    }).catch(() => {});
    await pg.waitForTimeout(1200);
    const frozen = await pg.evaluate(() => '<!DOCTYPE html>\n' + document.documentElement.outerHTML);
    writeFileSync(path.join(MIR, `${slug}.frozen.html`), frozen);
    ok++;
    if (ok % 5 === 0 || slugs.length <= 5) console.log(`  frozen ${ok}/${slugs.length} (${slug}, ${(frozen.length / 1024 | 0)}kB)`);
    await ctx.close();
  } catch (e) { fail++; console.error('  ! freeze failed', slug, e.message); }
}
await b.close();
srv.close();
console.log(`freeze done: ${ok} ok, ${fail} failed -> ${MIR}/<slug>.frozen.html`);
