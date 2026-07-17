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
  // EPS: mean pairwise Jaccard is a ratio sum — (1+0.7+0.7)/3 is exactly 0.8
  // mathematically but 0.7999999999999999 in IEEE-754, failing the frozen
  // >= 0.8 spec it satisfies (observed live). Tolerance implements the spec,
  // it does not lower the bar.
  const EPS = 1e-9;
  return Number(agreement) >= STABILITY_BAR - EPS && Number(coverage) >= MIN_COVERAGE_BAR - EPS;
}

// Protocol v2 cluster pass: STRICT majority of its sampled pages pass
// (k=3 -> >=2; k=2 -> 2; k=1 -> 1). Empty page list never passes.
export function clusterPassV2(pages) {
  const n = pages.length;
  return n > 0 && pages.filter(p => p.pass).length * 2 > n;
}

// ── diversity-aware per-cluster sampling (FIX A) ──────────────────────
// A single-cluster site (SPA pages have empty archetype features -> degenerate
// clustering) used to sample c.pages.slice(0,k) = the FIRST k pages, which are
// near-identical siblings; unrelated templates fell to passthrough and the G1
// contribution gate correctly went RED. These helpers spread the sample and
// widen it for a mega-cluster so the component model covers the real diversity.

// FROZEN constant — mega-cluster share above which a cluster is "dominant".
export const MEGA_CLUSTER_SHARE = 0.70;   // >= 70% of all inventory pages
// FROZEN constant — extra samples granted to a dominant cluster.
export const MEGA_CLUSTER_BOOST = 2;      // effective k = k + 2

// Evenly-spaced sample indexes into a cluster's page list: k picks whose indexes
// are round(i*(n-1)/(k-1)) for i in 0..k-1, deduped and ascending. k=1 -> [0]
// (v1-compat: the first page). k>=n -> every index. Never returns duplicates.
export function spreadIndexes(n, k) {
  if (n <= 0 || k <= 0) return [];
  if (k === 1) return [0];              // v1-compat path: first page only
  if (k >= n) return Array.from({ length: n }, (_, i) => i);
  const out = new Set();
  for (let i = 0; i < k; i++) out.add(Math.round(i * (n - 1) / (k - 1)));
  return [...out].sort((a, b) => a - b);
}

// Effective per-cluster k: base k, +MEGA_CLUSTER_BOOST when this cluster holds
// >= MEGA_CLUSTER_SHARE of ALL inventory pages (a degenerate mega-cluster).
export function effectivePerCluster(k, clusterPages, totalPages) {
  const base = Math.max(1, Number(k) || 1);
  if (totalPages > 0 && clusterPages / totalPages >= MEGA_CLUSTER_SHARE) {
    return base + MEGA_CLUSTER_BOOST;
  }
  return base;
}
