---
name: run-orchestration-loop
description: Operator runbook for executing a migration through the migration-orchestrator engine. Covers starting the engine (+ opencode), authoring a project plan from the template, submitting and watching a run, and answering the human HALT gates / epic rectifications. Use this BEFORE running any migration — the engine is a separate service that must be up first.
type: technical
status: active
allowed-tools: Bash, Read, Write, Edit
---

# Skill: Run a migration through the migration-orchestrator

The migration steps do not run themselves — they run as a **plan** submitted to the
**migration-orchestrator** engine (`migration-orchestrator/`, in this repo).
The engine drives OpenCode agents step by step and gates each step on a shell command
(`PROBE:`) that must exit 0. This skill is the operator runbook: bring the engine up,
author the plan, launch, and steer the human gates.

> Engine internals, plan schema, REST API, and config live in
> `migration-orchestrator/README.md`. This skill is the *operator* side.

## Mental model (read once)

- A **plan** is a tree: `goal` + `repo_dir` + **epics → stories → steps**. The migration's
  13 steps are already grouped into **6 epics** in `orchestration/plan-template.json` — you
  do **not** hand-build epics per project, you fill placeholders.
- Each step carries a `PROBE:` line in `acceptance_criteria`; the engine runs it with
  `cwd = repo_dir` and the step passes only on exit 0. That is the whole hardening.
- The agent model is set in `~/.config/opencode/opencode.jsonc`. The `model` field in the
  plan is cosmetic — do not rely on it.
- Some epics are **human-gated** (`auto_approve_on_max_rounds:false`) and the migration
  steps also raise explicit `status:halt` gates (Gate 0–5). The run pauses; you answer.

## Step 0 — Preconditions (check, don't assume)

```bash
# Jahia up (local)
curl -s -o /dev/null -w "jahia %{http_code}\n" http://localhost:8080/        # expect 302/200
# opencode CLI present + model configured
opencode --version
grep -m1 '"model"' ~/.config/opencode/opencode.jsonc
# engine venv installed
ls migration-orchestrator/.venv/bin/uvicorn                                   # exists?
```

If the venv is missing:
```bash
cd migration-orchestrator && python3 -m venv .venv && .venv/bin/pip install -e .
```

## Step 1 — Start the engine (once per machine session)

The engine spawns `opencode serve` itself; you only start the API.

```bash
cd migration-orchestrator
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8001 \
  > /tmp/orch.log 2>&1 &          # background; tail /tmp/orch.log to watch boot
# wait for opencode to report healthy (up to ~30s), then:
curl -s http://localhost:8001/health     # {"status":"ok","opencode":{...}}
```

- **Port is 8001** (config.py default + `run.sh`'s `ORCH_URL`).
- Web UI for live progress + gate buttons: **http://localhost:8001/app**.
  Build the UI first if `src/ui/` doesn't exist: `cd frontend && npm install && npm run build`.
- Runs persist in `orchestrator.db` (SQLite) across restarts.

## Step 2 — Prepare the project

A run targets one folder under `projects/<project>/` (that folder *is* the Jahia module,
created by the scaffold step). Before launch you need three things:

1. **`projects/<project>/.env`** — instance creds + MCP token (same local Jahia, so copy
   an existing one and keep it gitignored):
   ```bash
   mkdir -p projects/<project>
   cp projects/supercar-garage/.env projects/<project>/.env   # JAHIA_USER/HOST/MCP_TOKEN
   ```
2. **`orchestration/sitemaps/<project>.txt`** — the target **page** tree (structural pages
   only; articles/news are mainResource *content*, not page nodes). Build it from the
   reference `sitemap.xml` when reachable (even when the homepage WAFs):
   ```bash
   curl -s -A "Mozilla/5.0" https://<site>/sitemap.xml -o /tmp/sm.xml
   # parse the locale tree (e.g. /fr-FR), keep depth<=2 sections, drop article leaves + legal/utility
   ```
   Mirror the header comment style of `orchestration/sitemaps/supercar-garage.txt`
   (lowercase node names; defer legal/utility to vanity URLs).
3. **`orchestration/plans/<project>.plan.json`** — copy the template and replace every
   `__PLACEHOLDER__`:
   ```bash
   cp orchestration/plan-template.json orchestration/plans/<project>.plan.json
   # replace: __PROJECT__ __SITE_URL__ __NAMESPACE__ __MIX_NAMESPACE__
   #          __SITE_KEY__ __LANG__ __PAGES__ __REPO_ABS_PATH__
   python3 -c "import json;json.load(open('orchestration/plans/<project>.plan.json'))"  # must parse
   ```
   `__PAGES__` is comma-separated slugs, home first; `__REPO_ABS_PATH__` is this repo's
   absolute path; keep every `PROBE:` line verbatim.

> Reuse the per-project `.reference/` cache (see `capture-reference`) — never re-fetch.

## Step 3 — Launch

```bash
ORCH_URL=http://localhost:8001 bash orchestration/run.sh \
  orchestration/plans/<project>.plan.json --watch
```

`--watch` creates → starts → streams the SSE log. Drop it to only create (prints a
`run_id` you start later). Keep the `run_id` — it is your handle for everything below.

## Step 4 — Steer the human gates

The run pauses at gates. Watch `/app` or the SSE stream; act with curl:

```bash
ORCH=http://localhost:8001; RUN=<run_id>
# a step is waiting_human (Gate 0–5): answer it
curl -s -XPOST $ORCH/runs/$RUN/steps/<step_id>/answer -H 'Content-Type: application/json' \
     -d '{"answer":"approved — proceed"}'
# after an epic, the reviewer may propose rectification stories:
curl -s $ORCH/runs/$RUN/epics                                   # inspect proposal
curl -s -XPOST $ORCH/runs/$RUN/epics/<epic_id>/proposal/approve   # or .../reject
```

Gate discipline (the whole point of the harness): **do not rubber-stamp**. At each HALT
present the artifact the gate is about (analysis manifest, deployed shell screenshot,
reference-vs-Jahia diff) and only then answer. Gates map to:
`epic_foundation` (analysis), `epic_scaffold_assets`, `epic_content_model`,
`epic_components_templates` (deploy), `epic_content_quality` (content — human-gated),
`epic_fidelity_golive`.

## Step 5 — Control / recover

```bash
curl -s -XPOST $ORCH/runs/$RUN/pause            # / resume
curl -s -XPOST $ORCH/runs/$RUN/jump -d '{"step_id":"step_components","reset_dependents":true}'
curl -s -XPOST $ORCH/runs/$RUN/abort
curl -s $ORCH/runs/$RUN | jq '.status,.current_step_id'
```

A failing step retries to `max_attempts`, then blocks. Read its `PROBE:` output in the
SSE log / `/app`, fix the cause (often a probe finding), and `jump` back to it.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `run.sh` → "failed to create run" / connection refused | Engine not up. Start it (Step 1); `curl /health`. |
| Engine boots but steps hang at "running" | opencode not healthy — check `/tmp/orch.log`; confirm `opencode --version` + model in `opencode.jsonc`. |
| Probe passes locally but fails in the run | The verifier's `cwd` is `repo_dir` (absolute path in the plan). Make probe paths repo-relative; fix `__REPO_ABS_PATH__`. |
| Agent ran a different model than expected | Model is `opencode.jsonc`, not the plan. Edit there. |

## Definition of done for THIS skill

The engine answers `/health` ok, the plan parses and was accepted (`run_id` returned),
the run reaches `completed`, and every gate was answered against a real artifact — not
assumed.
