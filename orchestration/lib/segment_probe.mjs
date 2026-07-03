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
// GATE (QUALITY-PLAN P2.1 — pre-registered): a page passes only if the reply
// parses, references only REAL block ids, and covers >= --min-coverage (50) %
// of the content leaves. Unparseable/low-coverage replies get the exact error
// fed back and retried (--retries, default 3) — the gate is RED on persistent
// model failure, never silently green (the old gate passed on a total failure:
// unparseable -> 0 components -> everything passthrough -> "GREEN").
// STABILITY (P2.3): --stability 2 runs the gated segmentation twice; component
// root-set Jaccard >= 0.8 accepts (higher-coverage run wins), else a THIRD run
// decides by best-agreeing pair. Also dumps the data-seg-annotated DOM
// (<slug>.dom.html) for the deterministic segmentation->manifest adapter.
//
// Usage: node segment_probe.mjs <project> --pages <slug>[,slug2]
//        [--retries 3] [--min-coverage 50] [--stability 2]
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
// default page set (P2.2 multi-page): one representative per TEMPLATE CLUSTER
// (semantic-templates.json) — segmentation is per-cluster, not per-page
let defaultPages = inv.pages.slice(0, 1).map(p => p.slug);
try {
  const tpl = JSON.parse(fs.readFileSync(`${proj}/workflow-output/semantic-templates.json`, 'utf8'));
  const reps = (tpl.clusters || []).map(c => (c.pages || [])[0]).filter(Boolean);
  if (reps.length) defaultPages = reps;
} catch { /* keep single-page fallback */ }
const pageSel = typeof flags.pages === 'string' ? flags.pages.split(',').map(s => s.trim()) : defaultPages;

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

const RETRIES = Number(flags.retries) || 3;
const MIN_COVERAGE = Number(flags['min-coverage']) || 50;
const STABILITY = Number(flags.stability) || 2;

const server = await serveMirror(mirrorDir, loadRuntimeManifest(mirrorDir));
const base = `http://127.0.0.1:${server.port}`;
const browser = await chromium.launch({ headless: true });
const results = [];

// ── deterministic evaluation of one model reply against the outline ──
function makeEvaluator(nodes) {
  const rid = v => Number(v);
  const byId = new Map(nodes.map(n => [n.id, n]));
  const kids = new Map();
  nodes.forEach(n => { if (!kids.has(n.parent)) kids.set(n.parent, []); kids.get(n.parent).push(n.id); });
  const descendants = (id) => { const out = new Set([id]); const st = [id]; while (st.length) { for (const c of (kids.get(st.pop()) || [])) { out.add(c); st.push(c); } } return out; };
  const leaves = nodes.filter(n => n.leaf).map(n => n.id);
  return (comps) => {
    const refIds = comps.flatMap(c => [rid(c.rootId), ...((c.children || []).map(ch => rid(ch.rootId)))]);
    const roots = refIds.filter(id => byId.has(id));
    const covered = new Set();
    roots.forEach(id => descendants(id).forEach(d => covered.add(d)));
    const coveredLeaves = leaves.filter(id => covered.has(id));
    return {
      badIds: refIds.filter(id => !byId.has(id)),
      coverage: leaves.length ? +(100 * coveredLeaves.length / leaves.length).toFixed(1) : 100,
      passthrough: leaves.filter(id => !covered.has(id)),
      byId, rid,
    };
  };
}

// ── one GATED segmentation: retry with the exact failure fed back (P2.1) ──
async function segmentGated(nodes, shot, tag) {
  const evaluate = makeEvaluator(nodes);
  let feedback = '';
  let last = null;
  for (let attempt = 1; attempt <= RETRIES; attempt++) {
    const reply = await ovhVision(PROMPT(outlineText(nodes)) + feedback, shot);
    const parsed = extractJson(reply);
    if (!parsed || !Array.isArray(parsed.components)) {
      console.error(`    ${tag} attempt ${attempt}: UNPARSEABLE reply (${reply.length} chars)`);
      feedback = `\n\nYOUR PREVIOUS REPLY WAS NOT VALID JSON with a "components" array. Reply with STRICT JSON only.`;
      last = { comps: [], badIds: [], coverage: 0, passthrough: [], parseError: true };
      continue;
    }
    const comps = parsed.components;
    const ev = evaluate(comps);
    last = { comps, ...ev, parseError: false };
    if (ev.badIds.length) {
      console.error(`    ${tag} attempt ${attempt}: ${ev.badIds.length} hallucinated id(s) ${ev.badIds.slice(0, 8).join(',')}`);
      feedback = `\n\nERROR: these rootIds do not exist in the outline: ${ev.badIds.join(', ')}. Use ONLY ids from the outline.`;
      continue;
    }
    if (ev.coverage < MIN_COVERAGE) {
      console.error(`    ${tag} attempt ${attempt}: coverage ${ev.coverage}% < ${MIN_COVERAGE}%`);
      feedback = `\n\nERROR: your components cover only ${ev.coverage}% of the LEAF blocks — the target is >= ${MIN_COVERAGE}%. Uncovered leaf ids (cover the real content ones): ${ev.passthrough.slice(0, 30).join(', ')}.`;
      continue;
    }
    return { ...last, attempts: attempt, gatePass: true };
  }
  return { ...last, attempts: RETRIES, gatePass: false };
}

// ── stability (P2.3): N gated runs must agree (root-set Jaccard >= 0.8) ──
const jaccard = (a, b) => {
  const A = new Set(a), B = new Set(b);
  const inter = [...A].filter(x => B.has(x)).length;
  const uni = new Set([...A, ...B]).size;
  return uni ? inter / uni : 1;
};
const rootSet = (run) => run.comps.map(c => Number(c.rootId)).sort((x, y) => x - y);

async function segmentStable(nodes, shot, slug) {
  const runs = [await segmentGated(nodes, shot, `${slug}#1`)];
  if (STABILITY < 2) return { ...runs[0], agreement: null, runs: 1 };
  runs.push(await segmentGated(nodes, shot, `${slug}#2`));
  let agreement = jaccard(rootSet(runs[0]), rootSet(runs[1]));
  if (agreement >= 0.8) {
    const best = runs[0].coverage >= runs[1].coverage ? runs[0] : runs[1];
    return { ...best, agreement: +agreement.toFixed(3), runs: 2 };
  }
  console.error(`    ${slug}: stability Jaccard ${agreement.toFixed(2)} < 0.8 — third run (majority)`);
  runs.push(await segmentGated(nodes, shot, `${slug}#3`));
  let bi = 0, bj = 1, bestJ = -1;
  for (let i = 0; i < runs.length; i++) for (let j = i + 1; j < runs.length; j++) {
    const J = jaccard(rootSet(runs[i]), rootSet(runs[j]));
    if (J > bestJ) { bestJ = J; bi = i; bj = j; }
  }
  const pair = [runs[bi], runs[bj]];
  const best = pair[0].coverage >= pair[1].coverage ? pair[0] : pair[1];
  return { ...best, agreement: +bestJ.toFixed(3), runs: 3,
           gatePass: best.gatePass && bestJ >= 0.8 };
}

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
    // data-seg-annotated DOM — the deterministic bridge for the manifest
    // adapter (field re-extraction + skeleton generation per segment root)
    fs.writeFileSync(`${outDir}/${slug}.dom.html`, await page.content());
    await page.close();
    const shot = downscalePng(shotFull);
    // LEAF = terminal significant block (no significant-block descendant). Direct-text
    // detection is wrong for nested markup (text lives in descendant spans), so derive
    // it from the tree: the content units that must be covered are the terminal blocks.
    const hasChild = new Set(nodes.map(n => n.parent));
    nodes.forEach(n => { n.leaf = !hasChild.has(n.id); });
    rec.blocks = nodes.length; rec.leaves = nodes.filter(n => n.leaf).length;
    console.error(`  ${slug}: ${rec.blocks} blocks (${rec.leaves} leaves) → OVH ${OVH_VISION_MODEL} (${Math.round(shot.length / 1024)}KB img)`);

    const run = await segmentStable(nodes, shot, slug);
    const byId2 = new Map(nodes.map(n => [n.id, n]));
    const rid2 = v => Number(v);

    rec.components = run.comps.map(c => ({
      rootId: rid2(c.rootId), name: c.name, kind: c.kind,
      box: byId2.get(rid2(c.rootId)) ? (({ x, y, w, h, bg }) => ({ x, y, w, h, bg }))(byId2.get(rid2(c.rootId))) : null,
      children: (c.children || []).map(ch => ({ rootId: rid2(ch.rootId), name: ch.name, box: byId2.get(rid2(ch.rootId)) ? (({ x, y, w, h }) => ({ x, y, w, h }))(byId2.get(rid2(ch.rootId))) : null })),
    }));
    rec.passthrough = (run.passthrough || []).map(id => ({ ...byId2.get(id) }));
    rec.coverage = run.coverage;
    rec.hallucinatedIds = run.badIds || [];
    rec.attempts = run.attempts;
    rec.stabilityRuns = run.runs;
    rec.agreement = run.agreement;
    rec.gatePass = !!run.gatePass;        // parses + real ids + coverage >= MIN + stability
    rec.nodes = nodes;
    console.error(`  ${slug}: ${rec.components.length} components (${rec.components.filter(c => c.kind === 'container').length} containers), `
      + `leaf coverage ${rec.coverage}%, ${rec.passthrough.length} passthrough, attempts ${rec.attempts}, `
      + `stability ${rec.agreement === null ? 'n/a' : rec.agreement} (${rec.stabilityRuns} runs) → gate ${rec.gatePass ? 'GREEN' : 'RED'}`);
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
  console.log(`  ${r.slug}: ${r.components.length} components, coverage ${r.coverage}% leaves, passthrough ${r.passthrough.length}, `
    + `attempts ${r.attempts}, stability ${r.agreement === null ? 'n/a' : r.agreement}, gate ${r.gatePass ? 'GREEN' : 'RED'}`);
  for (const c of r.components) console.log(`     [${c.kind}] ${c.name}${c.children.length ? ' → ' + c.children.map(ch => ch.name).join(', ') : ''}`);
}
process.exit(results.every(r => r.ok && r.gatePass) ? 0 : 1);
