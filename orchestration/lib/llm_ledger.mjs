// llm_ledger.mjs — centralized per-project LLM usage ledger (JS side).
//
// Julian's standing requirement: EVERY OVH vision call and EVERY DeepSeek call is
// accounted for, per project, so cost/usage is never invisible. This is the JS
// half (Python half: orchestration/lib/llm_usage.py — same JSONL contract).
//
// Contract — append-only JSONL at  projects/<p>/llm-usage.jsonl  (PROJECT ROOT,
// deliberately NOT workflow-output, so it SURVIVES pipeline resets). One line/call:
//   {"ts": <iso8601>, "provider": "ovh"|"deepseek", "caller": "<tool[:detail]>",
//    "model": "...", "tokens_in": n|null, "tokens_out": n|null, "tokens_cache": n|null,
//    "meta": {...optional...} [, "usage_missing": true]}
//
// A response with no usage block is STILL logged (nulls + usage_missing:true) —
// the call COUNT must always be exact, that is the whole point of a ledger.
import fs from 'fs';
import path from 'path';

export const LEDGER_BASENAME = 'llm-usage.jsonl';

// Resolve the ledger file for a project. `projectPath` is anything that points at
// the project (e.g. "projects/supercar-garage", an absolute dir, or a bare project
// name). We normalise to <projectPath>/llm-usage.jsonl. A bare name like
// "supercar-garage" is treated as "projects/supercar-garage".
export function ledgerPath(projectPath) {
  if (!projectPath) return null;
  let p = String(projectPath).trim();
  if (!p) return null;
  // bare name with no slash -> assume it lives under projects/
  if (!p.includes('/') && !p.includes(path.sep)) p = path.join('projects', p);
  return path.join(p, LEDGER_BASENAME);
}

// Append one usage record. Never throws into the caller's hot path — a ledger
// write failure must not sink a real LLM result. Returns the file path on
// success, null if it could not resolve/write (and warns to stderr).
export function appendUsage(projectPath, record) {
  const file = ledgerPath(projectPath);
  if (!file) {
    process.stderr.write('[llm_ledger] no project path — usage NOT recorded\n');
    return null;
  }
  const line = {
    ts: record.ts || new Date().toISOString(),
    provider: record.provider ?? null,
    caller: record.caller ?? null,
    model: record.model ?? null,
    tokens_in: record.tokens_in ?? null,
    tokens_out: record.tokens_out ?? null,
    tokens_cache: record.tokens_cache ?? null,
  };
  if (record.meta && Object.keys(record.meta).length) line.meta = record.meta;
  if (record.usage_missing) line.usage_missing = true;
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.appendFileSync(file, JSON.stringify(line) + '\n');
    return file;
  } catch (e) {
    process.stderr.write(`[llm_ledger] append failed (${file}): ${e.message}\n`);
    return null;
  }
}

// Normalise an OpenAI-compatible `usage` object (OVH is OpenAI-shaped) into the
// ledger's {tokens_in, tokens_out, tokens_cache, usage_missing} shape. Defensive:
// providers differ on where cached tokens live, so probe several known spots.
// Returns usage_missing:true (and nulls) when there is no usable usage block.
export function normalizeOpenAIUsage(usage) {
  if (!usage || typeof usage !== 'object') {
    return { tokens_in: null, tokens_out: null, tokens_cache: null, usage_missing: true };
  }
  const tin = usage.prompt_tokens ?? usage.input_tokens ?? null;
  const tout = usage.completion_tokens ?? usage.output_tokens ?? null;
  // cached tokens: OpenAI/OVH nest under prompt_tokens_details.cached_tokens;
  // some providers surface a flat cached_tokens / prompt_cache_hit_tokens.
  const cache =
    usage.prompt_tokens_details?.cached_tokens ??
    usage.input_tokens_details?.cached_tokens ??
    usage.cached_tokens ??
    usage.prompt_cache_hit_tokens ??
    null;
  const missing = tin == null && tout == null;
  return { tokens_in: tin, tokens_out: tout, tokens_cache: cache, usage_missing: missing };
}
