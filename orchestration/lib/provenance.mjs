// provenance.mjs — shared provenance stamp for every pipeline artifact (P0).
// Mirror of provenance.py (keep the two in sync). Record:
//   { run_id:  ORCH_RUN_ID or null   (exported by the plan executors),
//     step_id: ORCH_STEP_ID or null,
//     generated_at: ISO-8601 UTC,
//     git_sha: short sha + "-dirty" when the worktree has any change,
//              null when git is unavailable (never crashes a producer),
//     tool: script basename, args: [argv strings],
//     page_set: [slugs processed by THIS invocation] or null }
// Placement: JSON dict artifacts embed "_provenance" (ADDITIVE, appended last);
// artifact DIRECTORIES (mirror/, reconstruct/, groundtruth/, segment/,
// zone-overlay/, compose/) get <dir>/provenance.json (LAST invocation wins);
// a single artifact file X.json gets a sibling X.provenance.json.
// Old artifacts without provenance stay valid — no consumer may require it.
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

let GIT_SHA;   // cached once per process (undefined = not computed yet)
function gitSha() {
  if (GIT_SHA !== undefined) return GIT_SHA;
  const cwd = path.dirname(fileURLToPath(import.meta.url));  // always inside the repo
  try {
    const opts = { cwd, stdio: ['ignore', 'pipe', 'ignore'], timeout: 10000 };
    const sha = execSync('git rev-parse --short=12 HEAD', opts).toString().trim();
    const dirty = execSync('git status --porcelain', opts).toString().trim();
    GIT_SHA = sha ? sha + (dirty ? '-dirty' : '') : null;
  } catch { GIT_SHA = null; }   // git absent/broken must never sink a producer
  return GIT_SHA;
}

export function provenanceDict(tool, args = null, pageSet = null) {
  return {
    run_id: process.env.ORCH_RUN_ID || null,
    step_id: process.env.ORCH_STEP_ID || null,
    generated_at: new Date().toISOString(),
    git_sha: gitSha(),
    tool,
    args: args !== null ? [...args] : process.argv.slice(2),
    page_set: pageSet !== null ? [...pageSet] : null,
  };
}

// Embed under "_provenance" (plain objects only, key appended LAST so existing
// keys keep their order). Arrays/scalars pass through untouched — sidecar-only.
export function stampJson(obj, tool, pageSet = null) {
  if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
    obj._provenance = provenanceDict(tool, null, pageSet);
  }
  return obj;
}

// X.json -> sibling X.provenance.json; a directory -> <dir>/provenance.json.
// Never throws — provenance must not sink a run.
export function writeSidecar(pathOrDir, tool, pageSet = null) {
  try {
    const isDir = fs.existsSync(pathOrDir) && fs.statSync(pathOrDir).isDirectory();
    const out = isDir
      ? path.join(pathOrDir, 'provenance.json')
      : (pathOrDir.endsWith('.json') ? pathOrDir.slice(0, -5) : pathOrDir) + '.provenance.json';
    fs.writeFileSync(out, JSON.stringify(provenanceDict(tool, null, pageSet), null, 2));
    return out;
  } catch { return null; }
}
