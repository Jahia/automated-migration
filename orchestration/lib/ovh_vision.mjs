// ovh_vision.mjs — thin client for OVH AI Endpoints (Qwen2.5-VL vision-language).
// DeepSeek has no vision; the segmentation decision needs to SEE the page, so the
// visual grouping call goes to Qwen2.5-VL-72B on OVH. Key from $OVH_API_KEY or the
// kepler provider block in ~/.config/opencode/opencode.jsonc (never committed).
import fs from 'fs';
import os from 'os';
import path from 'path';
import { PNG } from 'pngjs';

const OVH_URL = 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions';
export const OVH_VISION_MODEL = 'Qwen2.5-VL-72B-Instruct';

export function ovhKey() {
  if (process.env.OVH_API_KEY) return process.env.OVH_API_KEY;
  try {
    const cfg = fs.readFileSync(path.join(os.homedir(), '.config/opencode/opencode.jsonc'), 'utf8');
    const i = cfg.indexOf('kepler.ai.cloud.ovh');            // the OVH provider block
    const seg = cfg.slice(Math.max(0, i - 500), i);
    const keys = [...seg.matchAll(/"apiKey"\s*:\s*"([^"]+)"/g)].map(m => m[1]);
    if (keys.length) return keys[keys.length - 1];
  } catch { /* fall through */ }
  throw new Error('no OVH API key ($OVH_API_KEY or opencode.jsonc kepler block)');
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
export async function ovhVision(text, pngBuf, { maxTokens = 8000, temperature = 0, model = OVH_VISION_MODEL } = {}) {
  const key = ovhKey();
  const content = [{ type: 'text', text }];
  if (pngBuf) content.push({ type: 'image_url', image_url: { url: `data:image/png;base64,${pngBuf.toString('base64')}` } });
  const body = JSON.stringify({ model, max_tokens: maxTokens, temperature, messages: [{ role: 'user', content }] });
  const resp = await fetch(OVH_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body,
    signal: AbortSignal.timeout(180000),
  });
  if (!resp.ok) throw new Error(`OVH ${resp.status}: ${(await resp.text()).slice(0, 300)}`);
  const d = await resp.json();
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
