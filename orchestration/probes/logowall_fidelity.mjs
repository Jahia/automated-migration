// P6.2 targeted fidelity probe: compare the .asr-section-brands-logo ZONE only.
//   reference = source mirror en.html (offline-deterministic, same as groundtruth)
//   preview   = deployed Jahia EDIT render of the host page (home)
// Screenshots the SECTION element on each side, pixelmatch-compares.
// Reuses the exact offline/auth mechanics of groundtruth_probe.mjs.
import { chromium } from 'playwright';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import fs from 'fs';
import { serveMirror, offlineRoute, loadRuntimeManifest } from '../lib/mirror_net.mjs';
import { settlePage } from '../lib/settle.mjs';

const ROOT = '/Users/jmaurel/Documents/GitHub/jahiaMigration';
const proj = `${ROOT}/projects/discoverasr`;
const site = 'discoverasr';
const HOST = (process.env.JAHIA_URL || 'http://localhost:8081').replace(/\/$/, '');
const RAW_USER = process.env.JAHIA_USER || 'root';
const USER = RAW_USER.includes(':') ? RAW_USER.split(':')[0] : RAW_USER;
const PASS = RAW_USER.includes(':') ? RAW_USER.split(':').slice(1).join(':') : (process.env.JAHIA_PASS || 'root1234');
const mirrorDir = `${proj}/workflow-output/local-mirror`;
const outDir = `${proj}/workflow-output/groundtruth`;
fs.mkdirSync(outDir, { recursive: true });
const SEL = process.env.P62_SEL || '.logos-wrapper';
const VIEW = { width: 1440, height: 900 };

const runtimeManifest = loadRuntimeManifest(mirrorDir);
const { srv: mserver, port: mport } = await serveMirror(mirrorDir, runtimeManifest);
const mbase = `http://127.0.0.1:${mport}`;
const browser = await chromium.launch({ headless: true });

// ── reference: source mirror, offline ──
const ref = await browser.newPage({ viewport: VIEW });
await ref.route('**/*', offlineRoute(mbase, mirrorDir, runtimeManifest, null));
await ref.goto(`${mbase}/en.html`, { waitUntil: 'domcontentloaded', timeout: 45000 });
try { await ref.waitForLoadState('load', { timeout: 15000 }); } catch {}
await settlePage(ref);
const refEl = await ref.$(SEL);
if (!refEl) { console.error('FAIL: reference has no ' + SEL); process.exit(1); }
await refEl.scrollIntoViewIfNeeded();
await ref.waitForTimeout(500);
await refEl.screenshot({ path: `${outDir}/logowall.ref.png` });
const refBox = await refEl.boundingBox();
await ref.close();

// ── preview: authenticated Jahia EDIT render of the host page ──
const AUTH = 'Basic ' + Buffer.from(`${USER}:${PASS}`).toString('base64');
const ctx = await browser.newContext({
  viewport: VIEW,
  httpCredentials: { username: USER, password: PASS },
  extraHTTPHeaders: { Authorization: AUTH },
});
const jahiaHost = new URL(HOST).host;
const live = await ctx.newPage();
// keep the preview offline outside the Jahia host (rule 26 parity)
await live.route('**/*', (route) => {
  const u = new URL(route.request().url());
  if (u.host === jahiaHost || u.host === '127.0.0.1' || u.host === 'localhost') return route.continue();
  return offlineRoute(mbase, mirrorDir, runtimeManifest, null)(route);
});
const previewUrl = `${HOST}/cms/render/default/en/sites/${site}/home.html`;
await live.goto(previewUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
try { await live.waitForLoadState('load', { timeout: 15000 }); } catch {}
await settlePage(live);
const liveEl = await live.$(SEL);
if (!liveEl) { console.error('FAIL: preview has no ' + SEL); process.exit(1); }
await liveEl.scrollIntoViewIfNeeded();
await live.waitForTimeout(500);
await liveEl.screenshot({ path: `${outDir}/logowall.live.png` });
const liveBox = await liveEl.boundingBox();
await live.close();
await browser.close();
mserver.close();

// ── compare ──
const a = PNG.sync.read(fs.readFileSync(`${outDir}/logowall.ref.png`));
const b = PNG.sync.read(fs.readFileSync(`${outDir}/logowall.live.png`));
const w = Math.min(a.width, b.width), h = Math.min(a.height, b.height);
const crop = (png) => {
  const out = new PNG({ width: w, height: h });
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (png.width * y + x) << 2, j = (w * y + x) << 2;
    out.data[j] = png.data[i]; out.data[j+1] = png.data[i+1];
    out.data[j+2] = png.data[i+2]; out.data[j+3] = png.data[i+3];
  }
  return out;
};
const ca = crop(a), cb = crop(b);
const diff = new PNG({ width: w, height: h });
const mism = pixelmatch(ca.data, cb.data, diff.data, w, h, { threshold: 0.1 });
fs.writeFileSync(`${outDir}/logowall.diff.png`, PNG.sync.write(diff));
const total = w * h;
const pct = ((total - mism) / total) * 100;
console.log(JSON.stringify({
  ref: { w: a.width, h: a.height, box: refBox },
  live: { w: b.width, h: b.height, box: liveBox },
  compared: { w, h },
  mismatchPx: mism, totalPx: total,
  pixelIdentityPct: Number(pct.toFixed(2)),
}, null, 2));
