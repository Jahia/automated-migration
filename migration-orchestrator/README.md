# migration-orchestrator

A FastAPI engine that runs structured migration plans (**epics → stories → steps**),
and **proves** each step with shell commands instead of trusting the model's word.
A step passes only when every command it runs exits `0`.

Doctrine (P5.5): **the engine executes · the direct API judges · an in-engine tool
loop repairs.** The engine talks DIRECTLY to an OpenAI-compatible LLM API (DeepSeek by
default) — there is no OpenCode process anymore.

Part of the **jahiaMigration** harness — drives the 13-step migration pipeline
(see `../orchestration/`).

---

## How it works

You POST a **plan** to `/runs`. The plan is a tree: a run has **epics**, each epic has
**stories**, each story has **steps**. The engine walks steps in dependency order.

- A step whose acceptance criteria carry `Run: <cmd>` lines has a KNOWN, deterministic
  command at plan time — the **engine runs those lines itself** (same subprocess path as
  the probes). If they all pass, no LLM is invoked at all.
- Otherwise (or if a `Run:` line fails), the engine invokes the **RÉPARATEUR** role: a
  small in-engine tool loop (`read_file` / `bash` / `write_file`) driven by the direct
  LLM API. The model chooses actions; the engine executes them (same cwd/env as probes),
  audits each as `tool_executed`, and caps the loop by tool-call count and wall-clock.
- The step's final JSON envelope (`status`/`summary`/…) is parsed, then the **verifier**
  runs the acceptance `PROBE:` commands with `cwd` = the plan's `repo_dir`; **all must
  exit 0** or the step fails and retries (up to `max_attempts`).
- After every epic's stories complete, the engine runs an **epic review** — a single
  tool-free direct API call with `response_format: json_object`. The reviewer either
  approves or proposes **rectification** stories, which wait for human approval.
  Steps can also pause for a human (`waiting_human`) or halt the run.

---

## Prerequisites

- **Python ≥ 3.11** with the project venv installed (see Setup).
- **An OpenAI-compatible LLM API key** in `ORCHESTRATOR_LLM_API_KEY` (env or
  `migration-orchestrator/.env`, gitignored). `base_url` and `model` default to DeepSeek
  but are swappable — see "Which model runs?" below.
- `jq` and `curl` (used by `../orchestration/run.sh`).

## Setup

```bash
cd migration-orchestrator
python3 -m venv .venv
.venv/bin/pip install -e .          # installs fastapi, uvicorn, httpx, aiosqlite, sse-starlette, ...
# optional dev tools: .venv/bin/pip install -e '.[dev]'
```

Configuration is via env vars (prefix `ORCHESTRATOR_`) or a `.env` file (loaded from
`migration-orchestrator/.env`, gitignored). Copy `.env.example` to `.env` and set at
least `ORCHESTRATOR_LLM_API_KEY`. **Defaults are in `src/config.py` and are the source
of truth** — notably the API listens on **port 8001**.

## Build the web UI

The UI is not committed to the repo. Build it locally:

```bash
cd migration-orchestrator/frontend
npm install
npm run build    # outputs to ../src/ui/
```

For UI development with hot reload: `npm run dev` (Vite on http://localhost:5173).

## Start the engine

```bash
cd migration-orchestrator
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8001
# add --reload while developing the engine itself
```

On startup the lifespan handler:
1. constructs the direct LLM client from `ORCHESTRATOR_LLM_*` (no subprocess),
2. opens the SQLite store (`orchestrator.db`),
3. mounts the built web UI at **`/app`** (if `src/ui/` exists).

Verify it is up:

```bash
curl -s http://localhost:8001/health   # {"status":"ok","llm":{"configured":true,"model":"…","base_url":"…"}}
curl -s http://localhost:8001/runs      # [] (no runs yet)
open  http://localhost:8001/app         # web UI
```

Prove the key works with a tiny real call (prints only model + usage, never the key):

```bash
.venv/bin/python scripts/smoke_llm.py
```

## Run a plan

Submit + start + stream a plan (this is what `run.sh` wraps):

```bash
# from the jahiaMigration repo root:
ORCH_URL=http://localhost:8001 bash orchestration/run.sh orchestration/plans/<project>.plan.json --watch
```

## Which model runs?

The model is `ORCHESTRATOR_LLM_MODEL` (default `deepseek-v4-flash`), reached at
`ORCHESTRATOR_LLM_BASE_URL` (default `https://api.deepseek.com/v1`) with
`ORCHESTRATOR_LLM_API_KEY`. The provider stays swappable — point those three at any
OpenAI-compatible endpoint (DeepSeek, OVH, Mistral, vLLM, …) that speaks Chat
Completions with tool/function calling and `response_format`. The `model` field in a
plan is recorded in run state and used for cost accounting; the runtime model is the
config value.

---

## REST API

| Method + path | Purpose |
|---|---|
| `POST /runs` | create a run from a plan |
| `POST /runs/{id}/start` | start a created run |
| `GET  /runs` · `GET /runs/{id}` | list / detail |
| `GET  /runs/{id}/events` | SSE live event stream |
| `GET  /runs/{id}/stats` | per-run token/cost/duration metrics |
| `GET  /runs/{id}/audit` | structured audit log (JSONL) |
| `POST /runs/{id}/pause` · `/resume` | pause / resume |
| `POST /runs/{id}/jump` | jump to a step |
| `POST /runs/{id}/abort` · `/restart` | lifecycle |
| `POST /runs/{id}/steps/{step_id}/answer` | answer a `waiting_human` step |
| `GET  /runs/{id}/epics` · `GET /runs/{id}/epics/{epic_id}` | epic state |
| `POST /runs/{id}/epics/{epic_id}/proposal/approve` · `/reject` | rectification |
| `GET  /schema` | plan JSON schema |
| `GET  /health` | engine + LLM readiness (`{"status":"ok","llm":{"configured":bool,"model":…,"base_url":…}}`) |

## Configuration (env, prefix `ORCHESTRATOR_`)

| Var | Default | Notes |
|---|---|---|
| `ORCHESTRATOR_PORT` | `8001` | API port — keep in sync with `run.sh`'s `ORCH_URL` |
| `ORCHESTRATOR_HOST` | `0.0.0.0` | API bind host |
| `ORCHESTRATOR_LLM_API_KEY` | – | **required** — OpenAI-compatible API key (env or `.env`; never committed) |
| `ORCHESTRATOR_LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible endpoint (swap to change provider) |
| `ORCHESTRATOR_LLM_MODEL` | `deepseek-v4-flash` | model id |
| `ORCHESTRATOR_LLM_TIMEOUT` | `180` | per-call timeout (s) for judgment/repair turns |
| `ORCHESTRATOR_LLM_MAX_RETRIES` | `3` | transport-only retries (HTTP status errors are NOT retried) |
| `ORCHESTRATOR_REPAIR_MAX_TOOL_CALLS` | `24` | RÉPARATEUR tool-call cap |
| `ORCHESTRATOR_REPAIR_WALL_BUDGET_S` | `1500` | RÉPARATEUR wall-clock budget (s) |
| `ORCHESTRATOR_DB_PATH` | `orchestrator.db` | SQLite run store |
| `GITHUB_TOKEN` / `ORCHESTRATOR_GITHUB_REPO` | – | optional, for issue context |

## Repo layout

```
src/
├── main.py            # FastAPI app + lifespan (builds the direct LLM client, mounts /app)
├── config.py          # Settings (ORCHESTRATOR_* env; LLM base_url/model/key defaults)
├── orchestrator.py    # the loop: walk steps, verify, epic review, rectification, SSE
├── audit.py           # structured audit logger (per-run JSONL; probe/command/tool_executed)
├── llm_client.py      # direct OpenAI-compatible chat client (transport retries, no-4xx-retry)
├── repair_agent.py    # in-engine RÉPARATEUR tool loop + direct epic reviewer
├── llm_cost.py        # routes each response's usage → step counters + per-project ledger
├── verifier.py        # engine-runs Run: lines, runs PROBE:/commands_requested, all-exit-0 gate
├── models.py          # Pydantic plan + state models
├── persistence.py     # aiosqlite store
├── prompt_builder.py  # builds step and review prompts
├── routes/            # runs, steps, epics, events, stats, schema
└── ui/                # built web UI (not committed, build with frontend/)
frontend/              # UI source (Vite + React + Tailwind)
scripts/smoke_llm.py   # one real minimal LLM call (prints model + usage only)
PLANNER_INSTRUCTIONS.md# guidance for an LLM that authors plans
```

## See also

- `../orchestration/README.md` — how the migration harness maps its 13 steps onto 6 epics.
- `../.agents/skills/run-orchestration-loop/SKILL.md` — operator runbook.
- `PLANNER_INSTRUCTIONS.md` — for an LLM authoring a plan from scratch.
