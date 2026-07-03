// segment_probe_test.mjs — unit tests for the protocol-v2 pure helpers
// (segment_consensus.mjs). No browser, no vision endpoint, plain node:
//   node orchestration/lib/segment_probe_test.mjs
import assert from 'assert';
import {
  STABILITY_BAR, MIN_COVERAGE_BAR,
  jaccard, meanPairwiseJaccard, medoidIndex, consensusRootIds,
  pagePassV2, clusterPassV2,
} from './segment_consensus.mjs';

let n = 0;
const t = (name, fn) => { fn(); n++; console.log(`  ok ${name}`); };

// ── frozen bars ──
t('frozen bars', () => {
  assert.strictEqual(STABILITY_BAR, 0.8);
  assert.strictEqual(MIN_COVERAGE_BAR, 50);
});

// ── jaccard ──
t('jaccard identical', () => assert.strictEqual(jaccard([1, 2, 3], [3, 2, 1]), 1));
t('jaccard disjoint', () => assert.strictEqual(jaccard([1, 2], [3, 4]), 0));
t('jaccard partial', () => assert.strictEqual(jaccard([1, 2, 3], [2, 3, 4]), 0.5));
t('jaccard both empty = 1', () => assert.strictEqual(jaccard([], []), 1));
t('jaccard dedupes', () => assert.strictEqual(jaccard([1, 1, 2], [1, 2, 2]), 1));

// ── meanPairwiseJaccard ──
t('meanPairwise 3 runs, known value', () => {
  // J(a,b)=0.5, J(a,c)=1, J(b,c)=0.5 -> mean = 2/3
  const { agreement, pairwise } = meanPairwiseJaccard([[1, 2, 3], [2, 3, 4], [1, 2, 3]]);
  assert.strictEqual(pairwise.length, 3);
  assert.deepStrictEqual(pairwise.map(p => [p.i, p.j]), [[0, 1], [0, 2], [1, 2]]);
  assert.ok(Math.abs(agreement - 2 / 3) < 1e-9);
});
t('meanPairwise single run = 1, no pairs', () => {
  const { agreement, pairwise } = meanPairwiseJaccard([[1, 2]]);
  assert.strictEqual(agreement, 1);
  assert.strictEqual(pairwise.length, 0);
});
t('meanPairwise identical runs = 1', () => {
  assert.strictEqual(meanPairwiseJaccard([[5, 6], [5, 6], [5, 6]]).agreement, 1);
});

// ── medoidIndex ──
t('medoid picks the run closest to the others', () => {
  // run1 agrees with both others better than they agree with each other
  const sets = [[1, 2, 3, 9], [1, 2, 3], [2, 3, 4]];
  assert.strictEqual(medoidIndex(sets), 1);
});
t('medoid tie -> lowest index', () => {
  assert.strictEqual(medoidIndex([[1, 2], [1, 2], [1, 2]]), 0);
});
t('medoid single run -> 0', () => assert.strictEqual(medoidIndex([[1]]), 0));

// ── consensusRootIds ──
t('consensus = ids in >= ceil(N/2) runs (N=3 -> 2)', () => {
  assert.deepStrictEqual(consensusRootIds([[1, 2, 3], [2, 3, 4], [3, 4, 5]]),
    [2, 3, 4]);   // 1:1x 2:2x 3:3x 4:2x 5:1x
});
t('consensus numeric sort', () => {
  assert.deepStrictEqual(consensusRootIds([[10, 2], [10, 2], [10, 2]]), [2, 10]);
});
t('consensus N=1 keeps all ids', () => {
  assert.deepStrictEqual(consensusRootIds([[7, 3]]), [3, 7]);
});

// ── pagePassV2 (bars are >=, exact boundary passes) ──
t('pagePass at exact bars', () => assert.strictEqual(pagePassV2(0.8, 50), true));
t('pagePass agreement below bar', () => assert.strictEqual(pagePassV2(0.799, 90), false));
t('pagePass coverage below bar', () => assert.strictEqual(pagePassV2(0.95, 49.9), false));
t('pagePass discoverasr P4 value 0.733 stays RED', () => assert.strictEqual(pagePassV2(0.733, 68), false));
t('pagePass null agreement fails', () => assert.strictEqual(pagePassV2(null, 100), false));

// ── clusterPassV2 (STRICT majority) ──
const P = p => ({ pass: p });
t('cluster k=3: 2/3 passes', () => assert.strictEqual(clusterPassV2([P(true), P(true), P(false)]), true));
t('cluster k=3: 1/3 fails', () => assert.strictEqual(clusterPassV2([P(true), P(false), P(false)]), false));
t('cluster k=2: 1/2 fails (strict)', () => assert.strictEqual(clusterPassV2([P(true), P(false)]), false));
t('cluster k=2: 2/2 passes', () => assert.strictEqual(clusterPassV2([P(true), P(true)]), true));
t('cluster k=1: 1/1 passes', () => assert.strictEqual(clusterPassV2([P(true)]), true));
t('cluster k=1: 0/1 fails', () => assert.strictEqual(clusterPassV2([P(false)]), false));
t('cluster empty fails', () => assert.strictEqual(clusterPassV2([]), false));

console.log(`\nALL ${n} TESTS PASSED`);
