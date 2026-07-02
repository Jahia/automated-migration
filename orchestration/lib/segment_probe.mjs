// segment_probe.mjs — GENERIC component segmentation via a vision LLM (OVH Qwen2.5-VL).
//
// The altitude finder's fixed heuristics (heading class, bg keyword, >=3 row, filter
// bars…) overfit the test sites. Instead: render the page, hand the model a numbered
// outline of the block elements + a screenshot, and let it decide the component
// segmentation + HIERARCHY (container/children/chrome) the way a human editor would —
// no site-specific rules. Two hard invariants keep it safe and lossless:
//   1. PARTITION GATE (deterministic): the model may only reference block ids that
//      exist; every CONTENT LEAF ends up either inside a chosen component subtree or
//      in an explicit passthrough block — nothing is ever dropped (pixel-perfect).
//   2. per template CLUSTER, not per page (cheap at scale) + temp 0 + cached by hash.
//
// Output: workflow-output/segment/<slug>.segmentation.json + <slug>.segmap.html
//   (overlay coloured by kind: component / container / chrome / passthrough).
//
// Usage: node segment_probe.mjs <project> --pages <slug>[,slug2]
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { serveMirror, offlineRoute, loadRuntimeManifest } from './mirror_net.mjs';
import { ovhVision, downscalePng, extractJson, OVH_VISION_MODEL } from './ovh_vision.mjs';

const argv = process.argv.slice(2);
const flags = {}; const pos = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith('--')) { const k = a.slice(2); if (argv[i + 1] && !argv[i + 1].startsWith('--')) flags[k] = argv[++i]; else flags[k] = true; }
  else pos.push(a);
}
const proj = pos[0];
if (!proj) { console.error('usage: segment_probe.mjs <project> --pages slug[,slug2]'); process.exit(2); }
const mirrorDir = path.resolve(`${proj}/workflow-output/local-mirror`);
const outDir = `${proj}/workflow-output/segment`;
fs.mkdirSync(outDir, { recursive: true });
const inv = JSON.parse(fs.readFileSync(`${proj}/workflow-output/page-inventory.json`, 'utf8'));
const pageSel = typeof flags.pages === 'string' ? flags.pages.split(',').map(s => s.trim()) : inv.pages.slice(0, 1).map(p => p.slug);

// ── in-page: build a numbered outline of the significant block elements ──
// Each block gets a stable seg-id (data attr). We record tag, cleaned classes, a text
// snippet, bbox, background flag, depth, parent seg-id, and whether it is a CONTENT
// LEAF (carries its own text/media — the unit that must never be dropped).
const buildOutline = () => {
  const BLOCK = new Set(['DIV', 'SECTION', 'ARTICLE', 'ASIDE', 'FORM', 'UL', 'OL', 'LI', 'HEADER', 'FOOTER', 'NAV', 'MAIN', 'FIGURE']);
  const clean = c => (c || '').toString().split(/\s+/).map(t => t.indexOf('__') >= 0 ? t.slice(0, t.indexOf('__')) : t)
    .filter(t => t && !/^(css|sc|jsx)-/.test(t)).slice(0, 3).join(' ');
  const directText = el => { let s = ''; for (const n of el.childNodes) if (n.nodeType === 3) s += n.textContent; return s.replace(/\s+/g, ' ').trim(); };
  const hasBg = el => {
    const s = getComputedStyle(el);
    if (s.backgroundImage && s.backgroundImage !== 'none') return true;
    const bc = s.backgroundColor || '';
    const m = bc.match(/rgba?\(([^)]+)\)/); if (!m) return false;
    const [r, g, b, a = '1'] = m[1].split(',').map(x => parseFloat(x));
    return parseFloat(a) > 0.05 && !(r > 250 && g > 250 && b > 250);   // not transparent / not white
  };
  const isLeaf = el => directText(el).length >= 8 || el.matches('img,picture,video,svg,iframe') || (el.tagName === 'A' && el.getAttribute('href'));
  const significant = el => BLOCK.has(el.tagName) && (isLeaf(el)
    || [...el.children].filter(c => BLOCK.has(c.tagName)).length >= 1
    || el.matches('img,picture,video'));

  const nodes = []; let seg = 0;
  const walk = (el, depth, parentId) => {
    let myId = parentId;
    if (significant(el)) {
      const r = el.getBoundingClientRect();
      if (r.width > 2 && r.height > 2) {
        myId = ++seg;
        el.setAttribute('data-seg', String(myId));
        nodes.push({
          id: myId, parent: parentId, depth, tag: el.tagName.toLowerCase(),
          cls: clean(el.className), text: directText(el).slice(0, 60),
          x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY),
          w: Math.round(r.width), h: Math.round(r.height),
          bg: hasBg(el), leaf: isLeaf(el),
        });
      }
    }
    for (const c of el.children) walk(c, depth + 1, myId);
  };
  const root = document.querySelector('main,[role="main"]') || document.body;
  // include chrome regions as roots too
  for (const el of [document.querySelector('header'), root, document.querySelector('footer')]) if (el) walk(el, 0, 0);
  return nodes;
};

function outlineText(nodes) {
  // compact indented tree the model can reason over
  return nodes.map(n =>
    `${'  '.repeat(Math.min(n.depth, 8))}#${n.id} <${n.tag}${n.cls ? '.' + n.cls.replace(/ /g, '.') : ''}> `
    + `[${n.w}x${n.h}@${n.y}${n.bg ? ' BG' : ''}${n.leaf ? ' LEAF' : ''}]`
    + (n.text ? ` "${n.text}"` : '')
  ).join('\n');
}

const PROMPT = (ol) => `You are segmenting a web page into CMS components for a Jahia migration, exactly as a human content editor would model it.

You get a SCREENSHOT and a numbered OUTLINE of the page's block elements. Each line: #id <tag.class> [WxH@Ytop, BG=has background, LEAF=carries its own text/media] "text snippet".

Group the blocks into content components. Return STRICT JSON:
{"components":[{"rootId":<id>,"name":"<short editor-facing name>","kind":"component|container|chrome","children":[{"rootId":<id>,"name":"..."}]}]}

Rules:
- rootId MUST be an id from the outline. A component's DOM subtree (that id + its descendants) is what it owns.
- "container" = a section that groups repeated/sibling sub-cards → put each sub-card in "children" (e.g. a CTA band with a title + 2 cards; a card grid; a tabs/filter bar with its links). Prefer capturing the OUTERMOST wrapper that carries the section's background/heading as the container, so its background and title are owned by it.
- "component" = a single self-contained block (hero, rich text, media). "chrome" = site header / nav / footer / cookie bar.
- Choose roots so that TOGETHER they cover all LEAF blocks. Anything you don't assign will be kept as raw passthrough (so never force-fit — omit rather than mislabel), but aim to cover the real content.
- Names must be human/editorial (Hero, Article Card, Category Filter, CTA Section…), never CSS-hash or tag names.

OUTLINE:
${ol}

JSON only.`;

const server = await serveMirror(mirrorDir, loadRuntimeManifest(mirrorDir));
const base = `http://127.0.0.1:${server.port}`;
const browser = await chromium.launch({ headless: true });
const results = [];

for (const slug of pageSel) {
  const rec = { slug, model: OVH_VISION_MODEL };
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.route('**/*', offlineRoute(base, mirrorDir, loadRuntimeManifest(mirrorDir), null));
    await page.goto(`${base}/${slug}.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    try { await page.waitForLoadState('load', { timeout: 8000 }); } catch {}
    await page.waitForTimeout(1500);
    const nodes = await page.evaluate(buildOutline);
    const shotFull = await page.screenshot({ fullPage: true });
    fs.writeFileSync(`${outDir}/${slug}.page.png`, shotFull);
    rec.dims = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
    await page.close();
    const shot = downscalePng(shotFull);
    // LEAF = terminal significant block (no significant-block descendant). Direct-text
    // detection is wrong for nested markup (text lives in descendant spans), so derive
    // it from the tree: the content units that must be covered are the terminal blocks.
    const hasChild = new Set(nodes.map(n => n.parent));
    nodes.forEach(n => { n.leaf = !hasChild.has(n.id); });
    rec.blocks = nodes.length; rec.leaves = nodes.filter(n => n.leaf).length;
    console.error(`  ${slug}: ${rec.blocks} blocks (${rec.leaves} leaves) → OVH ${OVH_VISION_MODEL} (${Math.round(shot.length / 1024)}KB img)`);

    const reply = await ovhVision(PROMPT(outlineText(nodes)), shot);
    const parsed = extractJson(reply);
    const comps = (parsed && parsed.components) || [];

    // ── partition gate: validate ids, compute leaf coverage, passthrough the rest ──
    // the model returns ids as strings; coerce to Number to match node ids.
    const rid = v => Number(v);
    const byId = new Map(nodes.map(n => [n.id, n]));
    const descendants = (id) => { const out = new Set(); const rec2 = (p) => nodes.forEach(n => { if (n.parent === p) { out.add(n.id); rec2(n.id); } }); out.add(id); rec2(id); return out; };
    const refIds = comps.flatMap(c => [rid(c.rootId), ...((c.children || []).map(ch => rid(ch.rootId)))]);
    const allRoots = refIds.filter(id => byId.has(id));
    const covered = new Set(); allRoots.forEach(id => descendants(id).forEach(d => covered.add(d)));
    const leaves = nodes.filter(n => n.leaf).map(n => n.id);
    const coveredLeaves = leaves.filter(id => covered.has(id));
    const passthrough = leaves.filter(id => !covered.has(id));               // NOTHING dropped → passthrough
    const badIds = refIds.filter(id => !byId.has(id));

    rec.components = comps.map(c => ({
      rootId: rid(c.rootId), name: c.name, kind: c.kind,
      box: byId.get(rid(c.rootId)) ? (({ x, y, w, h, bg }) => ({ x, y, w, h, bg }))(byId.get(rid(c.rootId))) : null,
      children: (c.children || []).map(ch => ({ rootId: rid(ch.rootId), name: ch.name, box: byId.get(rid(ch.rootId)) ? (({ x, y, w, h }) => ({ x, y, w, h }))(byId.get(rid(ch.rootId))) : null })),
    }));
    rec.passthrough = passthrough.map(id => ({ ...byId.get(id) }));
    rec.coverage = leaves.length ? +(100 * coveredLeaves.length / leaves.length).toFixed(1) : 100;
    rec.hallucinatedIds = badIds;
    rec.gatePass = badIds.length === 0;   // every referenced id is real (nothing invented). coverage<100 is fine → passthrough.
    rec.nodes = nodes;
    console.error(`  ${slug}: ${rec.components.length} components (${rec.components.filter(c => c.kind === 'container').length} containers), `
      + `leaf coverage ${rec.coverage}%, ${passthrough.length} passthrough, ${badIds.length} hallucinated ids`);
    rec.ok = true;
  } catch (e) { rec.ok = false; rec.error = (e.message || String(e)).split('\n')[0]; console.error(`  ${slug}: FAIL ${rec.error}`); }
  results.push(rec);
}
await browser.close(); server.srv.close();

for (const r of results) {
  if (r.ok) { fs.writeFileSync(`${outDir}/${r.slug}.segmentation.json`, JSON.stringify(r, null, 2)); writeSegmap(r); }
}

// coloured component map — every region shown, NOTHING hidden. component=blue,
// container=green (+cyan children), chrome=grey, passthrough=amber (kept as raw HTML).
function writeSegmap(r) {
  const W = r.dims?.w || 1440, H = r.dims?.h || 1;
  const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const pct = (v, t) => (100 * v / t).toFixed(3) + '%';
  const box = (b, kind, label, z) => !b ? '' :
    `<div class="box ${kind}" style="left:${pct(b.x, W)};top:${pct(b.y, H)};width:${pct(b.w, W)};height:${pct(b.h, H)};z-index:${z}"><span>${esc(label)}</span></div>`;
  const parts = [];
  r.components.forEach((c, i) => {
    parts.push(box(c.box, c.kind, `${c.kind}: ${c.name}`, 10 + i));
    (c.children || []).forEach((ch, j) => parts.push(box(ch.box, 'child', ch.name, 40 + j)));
  });
  (r.passthrough || []).forEach((p, i) => parts.push(box(p, 'passthrough', 'passthrough', 5 + i)));
  const counts = `${r.components.length} components · ${r.components.filter(c => c.kind === 'container').length} containers · ${r.passthrough.length} passthrough · coverage ${r.coverage}%`;
  const html = `<!doctype html><meta charset=utf8><title>Segmentation — ${esc(r.slug)}</title><style>
   body{margin:0;background:#0f1115;color:#e6e6e6;font:13px/1.4 -apple-system,Segoe UI,sans-serif}
   header{padding:12px 20px;background:#171a21;border-bottom:1px solid #2a2f3a;position:sticky;top:0;z-index:9999}
   h1{font-size:15px;margin:0}small{color:#9aa4b2}
   .legend span{display:inline-block;margin-right:14px}.sw{display:inline-block;width:11px;height:11px;border-radius:2px;vertical-align:middle;margin-right:4px}
   .wrap{position:relative;max-width:1100px;margin:16px auto}.wrap img{display:block;width:100%}
   .box{position:absolute;box-sizing:border-box;border:2px solid;border-radius:3px}
   .box>span{position:absolute;left:0;top:-1px;font:10px/1.3 ui-monospace,monospace;padding:1px 5px;white-space:nowrap;color:#fff}
   .component{border-color:#0077bf;background:#0077bf18}.component>span{background:#0077bf}
   .container{border-color:#12b08a;background:#12b08a18}.container>span{background:#12b08a}
   .child{border-color:#00d3b8;border-style:dashed;background:#00d3b814}.child>span{background:#00a892}
   .chrome{border-color:#8a93a0;background:#8a93a012}.chrome>span{background:#6b7480}
   .passthrough{border-color:#e0952a;border-style:dashed;background:#e0952a1f}.passthrough>span{background:#c47f1e}
  </style>
  <header><h1>Segmentation — ${esc(r.slug)} <small>· OVH ${esc(r.model)} · ${counts}</small></h1>
  <div class=legend><span><i class="sw component"></i>component</span><span><i class="sw container"></i>container</span><span><i class="sw child"></i>child (sub-component)</span><span><i class="sw chrome"></i>chrome</span><span><i class="sw passthrough"></i>passthrough (raw HTML, kept)</span></div></header>
  <div class=wrap><img src="${esc(r.slug)}.page.png">${parts.join('')}</div>`;
  fs.writeFileSync(`${outDir}/${r.slug}.segmap.html`, html);
}
fs.writeFileSync(`${outDir}/segment-check.json`, JSON.stringify(
  { project: proj, model: OVH_VISION_MODEL, pages: results.map(({ nodes, ...r }) => r) }, null, 2));

console.log(`\n=== SEGMENTATION (OVH ${OVH_VISION_MODEL}) — ${proj} ===`);
for (const r of results) {
  if (!r.ok) { console.log(`  ${r.slug}: FAIL ${r.error}`); continue; }
  console.log(`  ${r.slug}: ${r.components.length} components, coverage ${r.coverage}% leaves, passthrough ${r.passthrough.length}, gate ${r.gatePass ? 'GREEN' : 'RED (hallucinated ids)'}`);
  for (const c of r.components) console.log(`     [${c.kind}] ${c.name}${c.children.length ? ' → ' + c.children.map(ch => ch.name).join(', ') : ''}`);
}
process.exit(results.every(r => r.ok && r.gatePass) ? 0 : 1);
