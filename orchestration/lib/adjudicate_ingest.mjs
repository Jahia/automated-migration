// adjudicate_ingest.mjs — GREEN-BY-ADJUDICATION ingestion (ASSIST-PLAN §4 B6).
//
// At a segmentation decision point the assistant (multimodal) reviews the rep
// pages' screenshots + segmap overlays and ADJUDICATES a component set per page,
// written as <PP>/workflow-output/segment/adjudication/<slug>.json:
//   {"components":[{"name":"News Carousel","rootId":<real block id>,
//                   "kind"?: "component|container|chrome",
//                   "children"?: [{"name":"...","rootId":<id>}]}],
//    "rationale":"...","adjudicator":"claude"}
//
// This tool makes hallucination IMPOSSIBLE: every rootId is validated against the
// REAL block-id universe of the page's existing <slug>.segmentation.json (the
// `nodes` outline segment_probe dumped); any unknown id → hard refuse (exit 1).
// Coverage is recomputed with segment_probe's exact leaf notion (terminal blocks:
// a node no other node claims as parent) and the frozen bar (>= 50) still applies.
// The stability bar is never silently waived — the previous measured agreement is
// carried as `previousAgreement`, and the page is recorded distinctly as
// greenBy: "adjudication" (segment_probe --consensus counts it green without
// re-running vision).
//
// No adjudication files → exit 0 no-op (safe to keep in the patched criteria).
//
// Usage: node adjudicate_ingest.mjs <projects/name>
import fs from 'fs';
import path from 'path';

const MIN_COVERAGE = 50;                       // FROZEN bar — never a flag

const pp = process.argv[2];
if (!pp) { console.error('usage: adjudicate_ingest.mjs <projects/name>'); process.exit(2); }
const segDir = path.join(pp, 'workflow-output', 'segment');
const adjDir = path.join(segDir, 'adjudication');

if (!fs.existsSync(adjDir)) { console.log(`[adjudicate_ingest] ${adjDir} absent — no-op`); process.exit(0); }
const files = fs.readdirSync(adjDir).filter(f => f.endsWith('.json')).sort();
if (!files.length) { console.log(`[adjudicate_ingest] no adjudication files in ${adjDir} — no-op`); process.exit(0); }

let failed = false;
const ingested = [];

for (const f of files) {
  const slug = f.replace(/\.json$/, '');
  const adjPath = path.join(adjDir, f);
  const segPath = path.join(segDir, `${slug}.segmentation.json`);

  let adj;
  try { adj = JSON.parse(fs.readFileSync(adjPath, 'utf8')); }
  catch (e) { console.error(`REFUSE ${slug}: ${adjPath} is not valid JSON (${e.message})`); failed = true; continue; }
  if (!Array.isArray(adj.components) || !adj.components.length) {
    console.error(`REFUSE ${slug}: ${adjPath} has no "components" array`); failed = true; continue;
  }

  if (!fs.existsSync(segPath)) {
    console.error(`REFUSE ${slug}: no existing ${segPath} — the block-id universe is unknown (run segment_probe first)`);
    failed = true; continue;
  }
  let prev;
  try { prev = JSON.parse(fs.readFileSync(segPath, 'utf8')); }
  catch (e) { console.error(`REFUSE ${slug}: ${segPath} unreadable (${e.message})`); failed = true; continue; }
  const nodes = prev.nodes || [];
  if (!nodes.length) {
    console.error(`REFUSE ${slug}: ${segPath} carries no nodes outline — cannot validate rootIds`);
    failed = true; continue;
  }

  // ── block universe + segment_probe's exact leaf/descendant notions ──
  const byId = new Map(nodes.map(n => [Number(n.id), n]));
  const kids = new Map();
  for (const n of nodes) {
    const p = Number(n.parent);
    if (!kids.has(p)) kids.set(p, []);
    kids.get(p).push(Number(n.id));
  }
  // LEAF = terminal significant block (no significant-block descendant) —
  // identical to segment_probe's post-hoc recompute (hasChild set).
  const hasChild = new Set(nodes.map(n => Number(n.parent)));
  const leaves = nodes.map(n => Number(n.id)).filter(id => !hasChild.has(id));
  const descendants = (id) => {
    const out = new Set([id]); const st = [id];
    while (st.length) for (const c of (kids.get(st.pop()) || [])) { out.add(c); st.push(c); }
    return out;
  };

  // ── validate EVERY referenced rootId against the universe ──
  const refIds = adj.components.flatMap(c =>
    [Number(c.rootId), ...((c.children || []).map(ch => Number(ch.rootId)))]);
  const badIds = refIds.filter(id => !Number.isFinite(id) || !byId.has(id));
  if (badIds.length) {
    console.error(`REFUSE ${slug}: ${badIds.length} rootId(s) not in the block universe of ${segPath}: `
      + `${badIds.slice(0, 12).join(', ')} (universe: ${nodes.length} blocks, ids 1..${Math.max(...byId.keys())})`);
    failed = true; continue;
  }

  // ── leaf coverage (segment_probe's notion) + frozen bar ──
  const covered = new Set();
  refIds.forEach(id => descendants(id).forEach(d => covered.add(d)));
  const coveredLeaves = leaves.filter(id => covered.has(id));
  const coverage = leaves.length ? +(100 * coveredLeaves.length / leaves.length).toFixed(1) : 100;
  const gatePass = coverage >= MIN_COVERAGE;
  const passthrough = leaves.filter(id => !covered.has(id)).map(id => ({ ...byId.get(id) }));

  const box = id => { const n = byId.get(id); return n ? { x: n.x, y: n.y, w: n.w, h: n.h, bg: n.bg } : null; };
  const components = adj.components.map(c => ({
    rootId: Number(c.rootId),
    name: c.name,
    kind: c.kind || 'component',
    box: box(Number(c.rootId)),
    children: (c.children || []).map(ch => {
      const b = box(Number(ch.rootId));
      return { rootId: Number(ch.rootId), name: ch.name, box: b && { x: b.x, y: b.y, w: b.w, h: b.h } };
    }),
  }));

  // ── write the adjudicated segmentation (base fields preserved so the
  //    downstream adapter — segment2manifest on <slug>.dom.html — still works) ──
  const rec = {
    ...prev,
    components,
    passthrough,
    coverage,
    hallucinatedIds: [],
    gatePass,
    adjudicated: true,
    greenBy: 'adjudication',
    rationale: adj.rationale || '',
    adjudicator: adj.adjudicator || 'claude',
    previousAgreement: prev.agreement ?? null,
    ok: true,
  };
  fs.writeFileSync(segPath, JSON.stringify(rec, null, 2));
  ingested.push({ slug, components: components.length, coverage, gatePass });
  console.log(`[adjudicate_ingest] ${slug}: ${components.length} components, leaf coverage ${coverage}% `
    + `(bar ${MIN_COVERAGE}) → ${gatePass ? 'GREEN-BY-ADJUDICATION' : 'RED (coverage below bar — not waived)'}; `
    + `previousAgreement=${rec.previousAgreement}`);
  if (!gatePass) failed = true;
}

if (failed) {
  console.error('[adjudicate_ingest] FAIL — at least one adjudication was refused or below the coverage bar');
  process.exit(1);
}
console.log(`[adjudicate_ingest] ingested ${ingested.length} adjudicated page(s)`);
process.exit(0);
