// llm_ledger_test.mjs — offline unit tests for the JS ledger half.
// No network, no LLM endpoint. Run:  node orchestration/lib/llm_ledger_test.mjs
import assert from 'assert';
import fs from 'fs';
import os from 'os';
import path from 'path';
import {
  ledgerPath, appendUsage, normalizeOpenAIUsage, LEDGER_BASENAME,
} from './llm_ledger.mjs';

let n = 0;
const t = (name, fn) => { fn(); n++; console.log(`  ok ${name}`); };

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ledger-'));

// ── ledgerPath resolution ──
t('ledgerPath appends basename to a projects/<p> path', () => {
  assert.strictEqual(ledgerPath('projects/foo'), path.join('projects/foo', LEDGER_BASENAME));
});
t('ledgerPath treats a bare name as projects/<name>', () => {
  assert.strictEqual(ledgerPath('foo'), path.join('projects', 'foo', LEDGER_BASENAME));
});
t('ledgerPath null on empty', () => assert.strictEqual(ledgerPath(''), null));

// ── append format ──
t('appendUsage writes one JSONL line with the full contract', () => {
  const proj = path.join(tmp, 'proj-a');
  const file = appendUsage(proj, {
    provider: 'ovh', caller: 'ovh_vision:segment_probe.mjs', model: 'Qwen2.5-VL-72B-Instruct',
    tokens_in: 100, tokens_out: 20, tokens_cache: 5, meta: { page: 'home', duration_ms: 42 },
  });
  assert.strictEqual(file, path.join(proj, LEDGER_BASENAME));
  const lines = fs.readFileSync(file, 'utf8').trim().split('\n');
  assert.strictEqual(lines.length, 1);
  const rec = JSON.parse(lines[0]);
  assert.strictEqual(rec.provider, 'ovh');
  assert.strictEqual(rec.tokens_in, 100);
  assert.strictEqual(rec.tokens_cache, 5);
  assert.strictEqual(rec.meta.page, 'home');
  assert.ok(rec.ts, 'ts is stamped');
  assert.ok(!('usage_missing' in rec), 'no usage_missing when usage present');
});

t('appendUsage is append-only (2 calls -> 2 lines)', () => {
  const proj = path.join(tmp, 'proj-b');
  appendUsage(proj, { provider: 'deepseek', caller: 'group_llm', model: 'm', tokens_in: 1, tokens_out: 1, tokens_cache: 0 });
  appendUsage(proj, { provider: 'deepseek', caller: 'group_llm', model: 'm', tokens_in: 2, tokens_out: 2, tokens_cache: 0 });
  const lines = fs.readFileSync(path.join(proj, LEDGER_BASENAME), 'utf8').trim().split('\n');
  assert.strictEqual(lines.length, 2);
});

// ── usage_missing path ──
t('appendUsage records usage_missing with nulls (call count preserved)', () => {
  const proj = path.join(tmp, 'proj-c');
  appendUsage(proj, { provider: 'ovh', caller: 'x', model: 'm', usage_missing: true });
  const rec = JSON.parse(fs.readFileSync(path.join(proj, LEDGER_BASENAME), 'utf8').trim());
  assert.strictEqual(rec.usage_missing, true);
  assert.strictEqual(rec.tokens_in, null);
  assert.strictEqual(rec.tokens_out, null);
});

// ── normalizeOpenAIUsage ──
t('normalizeOpenAIUsage: OVH/OpenAI shape', () => {
  const u = normalizeOpenAIUsage({ prompt_tokens: 900, completion_tokens: 100 });
  assert.deepStrictEqual([u.tokens_in, u.tokens_out, u.tokens_cache, u.usage_missing], [900, 100, null, false]);
});
t('normalizeOpenAIUsage: nested cached_tokens', () => {
  const u = normalizeOpenAIUsage({ prompt_tokens: 900, completion_tokens: 100, prompt_tokens_details: { cached_tokens: 64 } });
  assert.strictEqual(u.tokens_cache, 64);
});
t('normalizeOpenAIUsage: flat cached_tokens fallback', () => {
  const u = normalizeOpenAIUsage({ prompt_tokens: 5, completion_tokens: 1, cached_tokens: 3 });
  assert.strictEqual(u.tokens_cache, 3);
});
t('normalizeOpenAIUsage: null usage -> usage_missing', () => {
  const u = normalizeOpenAIUsage(null);
  assert.strictEqual(u.usage_missing, true);
  assert.strictEqual(u.tokens_in, null);
});

fs.rmSync(tmp, { recursive: true, force: true });
console.log(`\nALL ${n} LEDGER TESTS PASSED`);
