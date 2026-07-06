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
// PROTOCOL v2 (ASSIST-PLAN §7, pre-registered): --consensus runs N (--stability,
// default 3) gated segmentations UPFRONT per page; page agreement = MEAN pairwise
// Jaccard of the component root-sets; the emitted run is the MEDOID (max summed
// Jaccard vs the others); page PASS iff agreement >= 0.8 AND coverage >= 50 (both
// FROZEN constants — never flags). Pages are sampled per cluster (--per-cluster k),
// DIVERSITY-AWARE (FIX A): k pages SPREAD evenly across each cluster's page list
// (not the first k near-identical siblings), and a mega-cluster holding >= 70% of
// all inventory pages gets an effective k = k+2 (both frozen). cluster PASS =
// strict majority of its sampled pages; gate GREEN iff every cluster passes.
// segment-check.json switches to the
// v2 cluster shape and already-passing pages (protocol v2 or adjudicated) are
// skipped unless --force. WITHOUT --consensus, behavior is exactly v1 above.
//
// PER-PAGE MODE (component-model doctrine, 2026-07-06): --all-pages segments
// EVERY inventory page (no per-cluster sampling) and the v2 gate becomes
// EVERY page green (stability or adjudication) — strictly stronger than the
// cluster-majority gate. Frozen bars (0.8 / 50) unchanged. Rationale: sampled
// segmentation left unsampled pages' specific content as one anonymous rawHtml
// blob per page (signature matching only types RECURRING components).
//
// Usage: node segment_probe.mjs <project> --pages <slug>[,slug2]
//        [--retries 3] [--min-coverage 50] [--stability 2]
//        [--consensus] [--per-cluster k] [--all-pages] [--force]   (protocol v2)
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { serveMirror, offlineRoute, loadRuntimeManifest } from './mirror_net.mjs';
import { ovhVision, downscalePng, extractJson, OVH_VISION_MODEL, VISION_TEXT_ONLY } from './ovh_vision.mjs';
import { STABILITY_BAR, MIN_COVERAGE_BAR, meanPairwiseJaccard, medoidIndex, consensusRootIds, pagePassV2, clusterPassV2, spreadIndexes, effectivePerCluster } from './segment_consensus.mjs';

const argv = process.argv.slice(2);
const flags = {}; const pos = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith('--')) { const k = a.slice(2); if (argv[i + 1] && !argv[i + 1].startsWith('--')) flags[k] = argv[++i]; else flags[k] = true; }
  else pos.push(a);
}
const proj = pos[0];
if (!proj) { console.error('usage: segment_probe.mjs <project> --pages slug[,slug2] [--consensus] [--per-cluster k] [--force]'); process.exit(2); }
const CONSENSUS = !!flags.consensus;   // protocol v2 (ASSIST-PLAN §7)
const ALL_PAGES = !!flags['all-pages']; // per-page doctrine (2026-07-06): every page, every-green gate
const FORCE = !!flags.force;
const mirrorDir = path.resolve(`${proj}/workflow-output/local-mirror`);
const outDir = `${proj}/workflow-output/segment`;
fs.mkdirSync(outDir, { recursive: true });
const inv = JSON.parse(fs.readFileSync(`${proj}/workflow-output/page-inventory.json`, 'utf8'));
// default page set (P2.2 multi-page): one representative per TEMPLATE CLUSTER
// (semantic-templates.json) — segmentation is per-cluster, not per-page.
// --per-cluster k (B1) widens the sample to each cluster's pages. The sample is
// DIVERSITY-AWARE (FIX A): pages are SPREAD evenly across the cluster's list
// (spreadIndexes) rather than taken as the first k near-identical siblings, and
// a degenerate MEGA-CLUSTER (a single cluster holding >= 70% of all inventory
// pages, as SPA pages with empty archetype features collapse into) gets an
// effective k of k+2 (effectivePerCluster) so unrelated templates are covered
// instead of falling to passthrough (which pushed the G1 gate RED).
let defaultPages = inv.pages.slice(0, 1).map(p => p.slug);
const clusterOf = {};   // slug -> clusterId, for the v2 per-cluster gate
try {
  const tpl = JSON.parse(fs.readFileSync(`${proj}/workflow-output/semantic-templates.json`, 'utf8'));
  const perCluster = Math.max(1, Number(flags['per-cluster']) || 1);
  const totalPages = (tpl.clusters || []).reduce((s, c) => s + (c.pages || []).filter(Boolean).length, 0);
  const reps = [];
  for (const c of (tpl.clusters || [])) {
    const pages = (c.pages || []).filter(Boolean);
    for (const slug of pages) clusterOf[slug] = c.clusterId || 'unclustered';
    const k = effectivePerCluster(perCluster, pages.length, totalPages);
    for (const i of spreadIndexes(pages.length, k)) reps.push(pages[i]);
  }
  if (reps.length) defaultPages = reps;
} catch { /* keep single-page fallback */ }
if (ALL_PAGES) defaultPages = inv.pages.map(p => p.slug);   // per-page doctrine: no sampling
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

${VISION_TEXT_ONLY
  ? "You get a numbered OUTLINE of the page's block elements (no screenshot — judge the groupings from the geometry, nesting and text)."
  : 'You get a SCREENSHOT and a numbered OUTLINE of the page\'s block elements.'} Each line: #id <tag.class> [WxH@Ytop, BG=has background, LEAF=carries its own text/media] "text snippet".

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
// v1 stability default = 2 (best-pair protocol); v2 consensus default = 3 upfront runs.
const STABILITY = Number(flags.stability) || (CONSENSUS ? 3 : 2);
// scope rules in force (ASSIST-PLAN §5) — reported in the v2 segment-check.
// (The DOM-level application lives in the shared scope_rules library/consumers.)
let scopeRules = [];
try { scopeRules = JSON.parse(fs.readFileSync(`${proj}/workflow-output/scope-rules.json`, 'utf8')).rules || []; } catch { /* no rules file */ }

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

// ── protocol v2 (--consensus, ASSIST-PLAN §7): N UPFRONT gated runs ──
// agreement = MEAN pairwise Jaccard of root-sets; emitted run = MEDOID (max
// summed Jaccard vs the others); page pass = agreement >= 0.8 AND coverage >= 50
// (FROZEN bars from segment_consensus.mjs) — and the medoid run itself must have
// cleared the deterministic gate (parses, real ids only).
async function segmentConsensus(nodes, shot, slug, N) {
  const runs = [];
  for (let i = 1; i <= N; i++) runs.push(await segmentGated(nodes, shot, `${slug}#${i}`));
  const sets = runs.map(rootSet);
  const { agreement, pairwise } = meanPairwiseJaccard(sets);
  const mi = medoidIndex(sets);
  const chosen = runs[mi];
  const pass = chosen.gatePass && pagePassV2(agreement, chosen.coverage);
  console.error(`    ${slug}: consensus agreement ${agreement.toFixed(3)} over ${N} runs (medoid = run #${mi + 1})`);
  return { ...chosen, protocol: 'v2', consensus: true, runs: N,
           agreement: +agreement.toFixed(3), pairwise, chosenRun: mi + 1,
           consensusRootIds: consensusRootIds(sets, N), gatePass: pass };
}

// ── incremental (v2): a page already green under protocol v2, or adjudicated
// (B6 — adjudicate_ingest.mjs writes {adjudicated:true, gatePass:true}), is
// skipped and never re-sent to the vision model unless --force. ──
function priorPass(slug) {
  try {
    const s = JSON.parse(fs.readFileSync(`${outDir}/${slug}.segmentation.json`, 'utf8'));
    if (s.adjudicated === true && s.gatePass === true) return { greenBy: 'adjudication', s };
    if (s.protocol === 'v2' && s.gatePass === true) return { greenBy: 'stability', s };
  } catch { /* no prior segmentation */ }
  return null;
}

for (const slug of pageSel) {
  if (CONSENSUS && !FORCE) {
    const prior = priorPass(slug);
    if (prior) {
      console.error(`  ${slug}: SKIP — already green by ${prior.greenBy} (--force to re-run)`);
      results.push({ slug, ok: true, skipped: true, gatePass: true, protocol: 'v2',
                     greenBy: prior.greenBy, adjudicated: prior.s.adjudicated === true,
                     agreement: prior.s.agreement ?? null, coverage: prior.s.coverage ?? null,
                     attempts: prior.s.attempts ?? null, stabilityRuns: prior.s.stabilityRuns ?? null,
                     components: prior.s.components || [], passthrough: prior.s.passthrough || [],
                     model: prior.s.model || OVH_VISION_MODEL });
      continue;
    }
  }
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

    const run = CONSENSUS ? await segmentConsensus(nodes, shot, slug, STABILITY)
                          : await segmentStable(nodes, shot, slug);
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
    if (CONSENSUS) {                      // protocol v2 extras (segmentation.json contract)
      rec.protocol = 'v2';
      rec.consensus = true;
      rec.chosenRun = run.chosenRun;
      rec.pairwise = run.pairwise;
      rec.consensusRootIds = run.consensusRootIds;
      rec.greenBy = rec.gatePass ? 'stability' : null;
    }
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
  // skipped pages keep their existing (prior-green / adjudicated) segmentation.json untouched
  if (r.ok && !r.skipped) { fs.writeFileSync(`${outDir}/${r.slug}.segmentation.json`, JSON.stringify(r, null, 2)); writeSegmap(r); }
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
// ── protocol v2 (--consensus): cluster-grouped segment-check + majority gate ──
if (CONSENSUS) {
  const byCluster = new Map();
  for (const r of results) {
    const cid = clusterOf[r.slug] || 'unclustered';
    if (!byCluster.has(cid)) byCluster.set(cid, []);
    byCluster.get(cid).push({
      slug: r.slug,
      agreement: r.agreement ?? null,
      coverage: r.coverage ?? null,
      pass: !!(r.ok && r.gatePass),
      greenBy: (r.ok && r.gatePass) ? (r.greenBy || 'stability') : null,
    });
  }
  const clusters = [...byCluster.entries()].map(([id, pages]) => ({ id, pages, pass: clusterPassV2(pages) }));
  // --all-pages (per-page doctrine 2026-07-06): EVERY page must be green
  // (stability or adjudication) — strictly stronger than cluster majority.
  const gatePass = ALL_PAGES
    ? results.length > 0 && results.every(r => r.ok && r.gatePass)
    : clusters.length > 0 && clusters.every(c => c.pass);
  const rulesInForce = scopeRules.map(rl => rl.id).filter(Boolean);
  fs.writeFileSync(`${outDir}/segment-check.json`, JSON.stringify({
    protocol: 'v2', minCoverage: MIN_COVERAGE_BAR, stabilityBar: STABILITY_BAR,
    project: proj, model: OVH_VISION_MODEL, stabilityRuns: STABILITY,
    gateMode: ALL_PAGES ? 'all-pages' : 'cluster-majority',
    clusters, gatePass, rulesInForce,
  }, null, 2));
  console.log(`\n=== SEGMENTATION v2 consensus (OVH ${OVH_VISION_MODEL}) — ${proj} ===`);
  for (const c of clusters) {
    console.log(`  cluster ${c.id}: ${c.pass ? 'PASS' : 'FAIL'} (majority of ${c.pages.length} sampled)`);
    for (const p of c.pages) console.log(`    ${p.slug}: agreement ${p.agreement ?? 'n/a'}, coverage ${p.coverage ?? 'n/a'}%, ${p.pass ? `PASS (${p.greenBy})` : 'FAIL'}`);
  }
  if (rulesInForce.length) console.log(`  scope rules in force: ${rulesInForce.join(', ')}`);
  console.log(`  gate: ${gatePass ? 'GREEN' : 'RED'}`);
  process.exit(gatePass ? 0 : 1);
}

// ── v1 (no --consensus): unchanged output shape + per-page gate ──
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
