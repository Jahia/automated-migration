# migration-orchestrator

A FastAPI engine that runs structured migration plans (**epics → stories → steps**)
against [OpenCode](https://opencode.ai) coding agents, and **proves** each step with
shell commands instead of trusting the model's word. A step passes only when every
command it runs exits `0`.

Part of the **jahiaMigration** harness — drives the 13-step migration pipeline
(see `../orchestration/`).

---

## How it works

You POST a **plan** to `/runs`. The plan is a tree: a run has **epics**, each epic has
**stories**, each story has **steps**. The engine walks steps in dependency order; for
each step it opens an OpenCode session, sends the step prompt (the repo's `AGENTS.md` is
injected as the contract), and the agent returns a result that may include
`commands_requested`. The **verifier** runs those commands with `cwd` = the plan's
`repo_dir`; **all must exit 0** or the step fails and retries (up to `max_attempts`).
After every epic's stories complete, the engine runs an **epic review**; the reviewer
either approves or proposes **rectification** stories, which wait for human approval.
Steps can also pause for a human (`waiting_human`) or halt the run.

---

## Prerequisites

- **Python ≥ 3.11** with the project venv installed (see Setup).
- **OpenCode CLI** on `PATH` (`opencode --version`). The engine spawns `opencode serve`
  automatically on startup — you do **not** start it yourself.
- **An OpenCode model configured** in `~/.config/opencode/opencode.jsonc`. This is what
  the agents actually run as. See "Which model runs?" below.
- `jq` and `curl` (used by `../orchestration/run.sh`).

## Setup

```bash
cd migration-orchestrator
python3 -m venv .venv
.venv/bin/pip install -e .          # installs fastapi, uvicorn, httpx, aiosqlite, sse-starlette, ...
# optional dev tools: .venv/bin/pip install -e '.[dev]'
```

Configuration is via env vars (prefix `ORCHESTRATOR_`) or a `.env` file. Copy
`.env.example` to `.env` and adjust. **Defaults are in `src/config.py` and are the source
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
1. spawns `opencode serve --port 4096 --hostname 127.0.0.1` (the agent runtime),
2. waits up to 30s for it to report healthy,
3. opens the SQLite store (`orchestrator.db`),
4. mounts the built web UI at **`/app`** (if `src/ui/` exists).

Verify it is up:

```bash
curl -s http://localhost:8001/health        # {"status":"ok","opencode":{...}}
curl -s http://localhost:8001/runs           # [] (no runs yet)
open  http://localhost:8001/app              # web UI
```

## Run a plan

Submit + start + stream a plan (this is what `run.sh` wraps):

```bash
# from the jahiaMigration repo root:
ORCH_URL=http://localhost:8001 bash orchestration/run.sh orchestration/plans/<project>.plan.json --watch
```

## Which model runs?

**The agent model is whatever OpenCode is configured with in
`~/.config/opencode/opencode.jsonc`**. The `model` field in a plan and
`ORCHESTRATOR_OPENCODE_MODEL` in config are recorded in run state but are **not** passed
to OpenCode by the client — they are cosmetic. To change the model the agents use,
edit `opencode.jsonc`, not the plan.

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
| `GET  /health` | engine + opencode health |

## Configuration (env, prefix `ORCHESTRATOR_`)

| Var | Default | Notes |
|---|---|---|
| `ORCHESTRATOR_PORT` | `8001` | API port — keep in sync with `run.sh`'s `ORCH_URL` |
| `ORCHESTRATOR_HOST` | `0.0.0.0` | API bind host |
| `ORCHESTRATOR_OPENCODE_PORT` | `4096` | port for spawned `opencode serve` |
| `ORCHESTRATOR_OPENCODE_HOSTNAME` | `127.0.0.1` | |
| `ORCHESTRATOR_OPENCODE_MODEL` | `anthropic/claude-sonnet-4-5` | **cosmetic** — real model is in `opencode.jsonc` |
| `ORCHESTRATOR_DB_PATH` | `orchestrator.db` | SQLite run store |
| `GITHUB_TOKEN` / `ORCHESTRATOR_GITHUB_REPO` | – | optional, for issue context |

## Repo layout

```
src/
├── main.py            # FastAPI app + lifespan (spawns opencode serve, mounts /app)
├── config.py          # Settings (ORCHESTRATOR_* env)
├── orchestrator.py    # the loop: walk steps, verify, epic review, rectification, SSE
├── audit.py           # structured audit logger (per-run JSONL)
├── opencode_client.py # talks to opencode serve
├── verifier.py        # runs commands_requested, all-exit-0 gate
├── models.py          # Pydantic plan + state models
├── persistence.py     # aiosqlite store
├── prompt_builder.py  # builds step and review prompts
├── routes/            # runs, steps, epics, events, stats, schema
└── ui/                # built web UI (not committed, build with frontend/)
frontend/              # UI source (Vite + React + Tailwind)
PLANNER_INSTRUCTIONS.md# guidance for an LLM that authors plans
```

## See also

- `../orchestration/README.md` — how the migration harness maps its 13 steps onto 6 epics.
- `../.agents/skills/run-orchestration-loop/SKILL.md` — operator runbook.
- `PLANNER_INSTRUCTIONS.md` — for an LLM authoring a plan from scratch.
