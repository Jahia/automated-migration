// segment_consensus.mjs — pure helpers for segmentation stability protocol v2
// (ASSIST-PLAN §7, pre-registered 2026-07-03). Extracted from segment_probe.mjs so
// they are unit-testable with plain node (segment_probe_test.mjs) — no browser, no
// vision endpoint.
//
// FROZEN bars (pre-registration clause): these are CONSTANTS, never CLI flags.
// They may only change with a dated amendment to ASSIST-PLAN/QUALITY-PLAN.
export const STABILITY_BAR = 0.8;     // page agreement bar (mean pairwise Jaccard)
export const MIN_COVERAGE_BAR = 50;   // page leaf-coverage bar (%)

// Jaccard similarity of two id lists (identical to the v1 implementation).
export const jaccard = (a, b) => {
  const A = new Set(a), B = new Set(b);
  const inter = [...A].filter(x => B.has(x)).length;
  const uni = new Set([...A, ...B]).size;
  return uni ? inter / uni : 1;
};

// Mean pairwise Jaccard over N root-sets (protocol v2 page agreement).
// Returns { agreement, pairwise: [{i, j, jaccard}] } with pairs in (i<j) order.
// agreement is computed from UNROUNDED values; pairwise entries are rounded for
// the report only. Zero pairs (N=1) => agreement 1 (a single run agrees with itself).
export function meanPairwiseJaccard(sets) {
  const raw = [];
  for (let i = 0; i < sets.length; i++)
    for (let j = i + 1; j < sets.length; j++)
      raw.push({ i, j, jaccard: jaccard(sets[i], sets[j]) });
  const agreement = raw.length ? raw.reduce((s, p) => s + p.jaccard, 0) / raw.length : 1;
  return { agreement, pairwise: raw.map(p => ({ ...p, jaccard: +p.jaccard.toFixed(3) })) };
}

// Medoid run = the run whose root-set has the MAX summed Jaccard vs all the
// others (the run "closest to consensus"). Ties break to the LOWEST index
// (deterministic; earlier run wins).
export function medoidIndex(sets) {
  let best = 0, bestSum = -Infinity;
  for (let i = 0; i < sets.length; i++) {
    let s = 0;
    for (let j = 0; j < sets.length; j++) if (j !== i) s += jaccard(sets[i], sets[j]);
    if (s > bestSum) { bestSum = s; best = i; }
  }
  return best;
}

// Consensus root-set: ids present in >= ceil(N/2) of the N runs, numeric ascending.
export function consensusRootIds(sets, n = sets.length) {
  const need = Math.ceil(n / 2);
  const count = new Map();
  for (const s of sets) for (const id of new Set(s)) count.set(id, (count.get(id) || 0) + 1);
  return [...count.entries()].filter(([, c]) => c >= need).map(([id]) => id).sort((a, b) => a - b);
}

// Protocol v2 page pass: agreement >= 0.8 AND coverage >= 50 (frozen bars).
export function pagePassV2(agreement, coverage) {
  return Number(agreement) >= STABILITY_BAR && Number(coverage) >= MIN_COVERAGE_BAR;
}

// Protocol v2 cluster pass: STRICT majority of its sampled pages pass
// (k=3 -> >=2; k=2 -> 2; k=1 -> 1). Empty page list never passes.
export function clusterPassV2(pages) {
  const n = pages.length;
  return n > 0 && pages.filter(p => p.pass).length * 2 > n;
}
