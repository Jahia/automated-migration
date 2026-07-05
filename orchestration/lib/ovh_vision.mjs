// ovh_vision.mjs — thin client for OVH AI Endpoints (Qwen2.5-VL vision-language).
// DeepSeek has no vision; the segmentation decision needs to SEE the page, so the
// visual grouping call goes to Qwen2.5-VL-72B on OVH. Key from $OVH_API_KEY or the
// kepler provider block in ~/.config/opencode/opencode.jsonc (never committed).
import fs from 'fs';
import os from 'os';
import path from 'path';
import { PNG } from 'pngjs';
import { appendUsage, normalizeOpenAIUsage } from './llm_ledger.mjs';

// Provider override (VISION_* env, injected into probes via the repo .env.local):
// point the segmentation at any OpenAI-compatible endpoint. Text-only endpoints
// (DeepSeek rejects the `image_url` content variant outright with a 400) must also
// set VISION_TEXT_ONLY=1 so the screenshot part is dropped from the request — the
// numbered outline (tag/class, geometry, BG/LEAF flags, snippets) carries the call.
const VISION_URL = process.env.VISION_BASE_URL
  ? process.env.VISION_BASE_URL.replace(/\/+$/, '') + '/chat/completions'
  : 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions';
export const OVH_VISION_MODEL = process.env.VISION_MODEL || 'Qwen2.5-VL-72B-Instruct';
export const VISION_TEXT_ONLY = process.env.VISION_TEXT_ONLY === '1';
// Per-call abort. 180s fits OVH vision; a text-only endpoint emitting the full
// components JSON for a 400+ block outline can legitimately run longer.
const VISION_TIMEOUT_MS = Number(process.env.VISION_TIMEOUT_MS) || 180000;
const VISION_PROVIDER = !process.env.VISION_BASE_URL ? 'ovh'
  : VISION_URL.includes('deepseek') ? 'deepseek-direct' : 'custom';

// ── LLM usage ledger wiring ───────────────────────────────────────
// ovh_vision doesn't own a project context. The ONLY in-code caller today is
// segment_probe.mjs, which is off-limits to edit — so the project is resolved
// zero-touch, in priority order:
//   1. an explicit `ledgerProject` in the ovhVision options (future wiring),
//   2. setLedgerProject(p) set by a caller before the call,
//   3. the LLM_LEDGER_PROJECT env var (the engine passes env through to probes),
//   4. an argv scan for a "projects/<name>" token — every real invocation is
//      `node .../segment_probe.mjs projects/<name> ...`, so this is reliable.
// This means segment_probe's vision calls are ledgered WITHOUT touching it.
let _ledgerProject = null;
export function setLedgerProject(p) { _ledgerProject = p || null; }

// Scan argv for a projects/<name> token (or a --project <name> flag). Returns the
// projects/<name> path so the ledger lands at projects/<name>/llm-usage.jsonl.
function projectFromArgv() {
  // Scan from argv[1] so both `node script.mjs projects/x` (real invocation, the
  // token is at [2]) and the `node -e` layout (token at [1]) are covered; the
  // script path itself never matches the projects/<name> pattern.
  const argv = process.argv.slice(1);
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--project' && argv[i + 1]) {
      const v = argv[i + 1];
      return v.includes('projects/') ? v : `projects/${v}`;
    }
    const m = a.match(/(?:^|\/)projects\/([^/\s]+)/);
    if (m) return `projects/${m[1]}`;
  }
  return null;
}

export function resolveLedgerProject(explicit) {
  return explicit || _ledgerProject || process.env.LLM_LEDGER_PROJECT || projectFromArgv() || null;
}

export function ovhKey() {
  if (process.env.VISION_API_KEY) return process.env.VISION_API_KEY;
  if (process.env.OVH_API_KEY) return process.env.OVH_API_KEY;
  try {
    const cfg = fs.readFileSync(path.join(os.homedir(), '.config/opencode/opencode.jsonc'), 'utf8');
    const i = cfg.indexOf('kepler.ai.cloud.ovh');            // the OVH provider block
    const seg = cfg.slice(Math.max(0, i - 500), i);
    const keys = [...seg.matchAll(/"apiKey"\s*:\s*"([^"]+)"/g)].map(m => m[1]);
    if (keys.length) return keys[keys.length - 1];
  } catch { /* fall through */ }
  throw new Error('no vision API key ($VISION_API_KEY, $OVH_API_KEY or opencode.jsonc kepler block)');
}

// Downscale a PNG buffer to <= maxW wide and <= maxH tall by an INTEGER box average
// (fast, dependency-free). Vision models don't need full-res; a tall page screenshot
// must be shrunk to fit context. Returns a PNG buffer.
export function downscalePng(buf, maxW = 820, maxH = 4000) {
  const src = PNG.sync.read(buf);
  const fx = Math.ceil(src.width / maxW), fy = Math.ceil(src.height / maxH);
  const f = Math.max(1, fx, fy);
  if (f === 1) return buf;
  const w = Math.floor(src.width / f), h = Math.floor(src.height / f);
  const out = new PNG({ width: w, height: h });
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let r = 0, g = 0, b = 0, a = 0, n = 0;
      for (let dy = 0; dy < f; dy++) for (let dx = 0; dx < f; dx++) {
        const si = ((y * f + dy) * src.width + (x * f + dx)) << 2;
        r += src.data[si]; g += src.data[si + 1]; b += src.data[si + 2]; a += src.data[si + 3]; n++;
      }
      const di = (y * w + x) << 2;
      out.data[di] = r / n; out.data[di + 1] = g / n; out.data[di + 2] = b / n; out.data[di + 3] = a / n;
    }
  }
  return PNG.sync.write(out);
}

// One vision+text call. `text` is the prompt, `pngBuf` the (already-downscaled) image.
// Returns the assistant's raw string. maxTokens generous (the model reasons + emits JSON).
export async function ovhVision(text, pngBuf, { maxTokens = 8000, temperature = 0, model = OVH_VISION_MODEL, ledgerProject, caller } = {}) {
  const key = ovhKey();
  const content = [{ type: 'text', text }];
  if (pngBuf && !VISION_TEXT_ONLY) content.push({ type: 'image_url', image_url: { url: `data:image/png;base64,${pngBuf.toString('base64')}` } });
  const body = JSON.stringify({ model, max_tokens: maxTokens, temperature, messages: [{ role: 'user', content }] });
  const project = resolveLedgerProject(ledgerProject);
  const callerName = caller || `ovh_vision:${(process.argv[1] && path.basename(process.argv[1])) || 'unknown'}`;
  const t0 = Date.now();
  const resp = await fetch(VISION_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body,
    signal: AbortSignal.timeout(VISION_TIMEOUT_MS),
  });
  // Ledger EVERY call that produced a response — success AND failed-with-response
  // (the call was billed regardless). Only a thrown network error (no response)
  // goes unlogged, and that call did not reach the endpoint.
  const record = (usage, extraMeta) => {
    const u = normalizeOpenAIUsage(usage);
    appendUsage(project, {
      provider: VISION_PROVIDER, caller: callerName, model,
      tokens_in: u.tokens_in, tokens_out: u.tokens_out, tokens_cache: u.tokens_cache,
      usage_missing: u.usage_missing,
      meta: { duration_ms: Date.now() - t0, ...(extraMeta || {}) },
    });
  };
  if (!resp.ok) {
    const errText = (await resp.text()).slice(0, 300);
    record(null, { status: resp.status, error: true });
    throw new Error(`${VISION_PROVIDER} ${resp.status}: ${errText}`);
  }
  const d = await resp.json();
  record(d.usage, { status: resp.status });
  return d.choices?.[0]?.message?.content ?? '';
}

// Extract the first JSON object/array from a possibly ```-fenced model reply.
export function extractJson(s) {
  const fence = s.match(/```(?:json)?\s*([[{][\s\S]*?[\]}])\s*```/);
  const raw = fence ? fence[1] : s.slice(Math.min(...[s.indexOf('{'), s.indexOf('[')].filter(i => i >= 0).concat([s.length])));
  try { return JSON.parse(raw); } catch { /* try to trim trailing noise */ }
  // last resort: from first bracket to its matching close
  const start = Math.min(...['{', '['].map(c => s.indexOf(c)).filter(i => i >= 0));
  if (start < 0) return null;
  const open = s[start], close = open === '{' ? '}' : ']';
  let depth = 0;
  for (let i = start; i < s.length; i++) {
    if (s[i] === open) depth++;
    else if (s[i] === close && --depth === 0) { try { return JSON.parse(s.slice(start, i + 1)); } catch { return null; } }
  }
  return null;
}
