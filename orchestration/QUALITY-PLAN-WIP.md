# QUALITY-PLAN — WIP state dump (2026-07-03, session stopped on quota)

> **RESOLVED 2026-07-03 (same day, later session): the 3 defects below are fixed, pytest is
> 16/16 (4 new regression tests), and P0 is committed. Next step: P1 (tasks #15→18, artifact
> bridge + minimal passthrough — see §"Exact resume steps" item 5 for the recon facts).**
> The rest of this file is kept as the historical record of the stop point.

> Resume anchor. Read `orchestration/QUALITY-PLAN.md` first (the governing plan, pre-registered
> thresholds). This file records exactly where execution stopped: **P0 is implemented and
> verified but NOT committed, with 3 known defects left to fix.**

## Where we are

- **QUALITY-PLAN.md written** (untracked, ready to commit). Task tracker: P0=#14 (in_progress),
  P1=#15-18, P2=#19, P3=#20, P4=#21.
- **P0 implemented by a 3-agent workflow, then verified** (mechanical verifier: ALL GREEN;
  adversarial verifier: 3 real defects found, see below). **Nothing committed.**
- A fix agent for the 3 defects was launched then **stopped before it made any edit**
  (pytest still 12/12, no new test files beyond the P0 ones).

## What is in the working tree (uncommitted, all verified green)

P0.1+0.2 — env truth + secrets (live-verified against real Jahia):
- `.env.example` (NEW, committed-ready), `.gitignore` (covers `.env.local`), `.env.local`
  (NEW, **gitignored, holds the real values for THIS machine — base URL `http://localhost:8081`
  and the real super-user credentials; never committed**).
- `orchestration/probes/_lib.sh` — `load_env` seeds defaults from repo-root `.env.local`
  (never clobbers caller env or project `.env`), maps `JAHIA_URL`↔`JAHIA_HOST`, composes
  `user:pass`; all 14 load_env probes inherit. `fidelity.sh`, `render-truth.sh` now call load_env;
  `publish-parity.py`, `content-fidelity.py` read env with old values as fallbacks;
  `orchestration/lib/mcp_client.py` seeds from repo-root `.env.local` (cwd-safe).
- `migration-orchestrator/src/verifier.py` — `probe_env()` merges `<repo_dir>/.env.local` into
  probe subprocess env; `config.py` gains `env_file` + `ORCHESTRATOR_ENV_FILE`.
- `CLAUDE.md` + `.claude/rules/jahia.md` — URLs/creds from `.env.local`; **this machine's Jahia
  is :8081; port 8080 is an unrelated email-sorter container**; Origin must match `$JAHIA_URL`.
- Live checks passed: `connect.sh` + `mcp.sh` PASS from clean env; GraphQL `currentUser`=root.

P0.3 — engine gate integrity (12/12 pytest green):
- `models.py` `StepStatus.rejected`; `orchestrator.py` `approve_gate` = ONLY halted→done path,
  `reject_gate` persists; both silent halted→done normalizations REMOVED (resume refuses while a
  halted/rejected step exists); `state.py` `lint_plan` (deploy|content|publish|scaffold ⇒ ≥1 PROBE,
  HTTP 400 with offenders; all 8 committed plans pass); `_infer_gate_type` + `deploy`/`groundtruth`;
  `PROBE[NNN]:` per-probe timeout + `ORCHESTRATOR_PROBE_TIMEOUT`; `routes/runs.py` typed endpoints.
- `migration-orchestrator/tests/{conftest.py,test_gate_integrity.py}` (NEW) — 12 tests.
- `CONTROL-LOOP.md` rewritten for the new approve/reject contract.

P0.4 — doc honesty:
- `ANALYZE-PIPELINE.md` thesis "deterministic"→"verifiable" (+ pointer to QUALITY-PLAN.md),
  `README.md` pointer, `.claude/rules/migration.md` rule 9 corrected (j:linkType inline;
  j:url/j:linknode NEVER declared; confirming mutation scheduled at first v2 deploy).

⚠️ Also in `git status` but NOT part of P0 (pre-existing, do not mix into the P0 commit):
`projects/supercar-garage/workflow-output/*` deletions + `component-manifest.json` modification,
`docker/deps/`, `migration-orchestrator/logs/`, `migration-orchestrator/migration-orchestrator/`.

## MUST FIX before committing P0 (adversarial review, confirmed by simulation)

1. `migration-orchestrator/src/state.py` `normalize_for_resume` (~247-268): a story persisted as
   `running` (recorded at halt) is never reset; `select_next_ready_story` only picks `pending` →
   **approve_gate after an engine restart instantly fails epic+run** while the endpoint returns
   approved. Fix: story `running` with runnable (pending) steps → `pending`; mirror for epics.
2. `migration-orchestrator/src/orchestrator.py` `jump_to_step` (~950-964): with no active loop
   (engine restarted) it sets `forced_next_step` + flips run to `running` but **spawns no fresh
   `_run_loop`** → zombie run; subsequent resume refused. Fix: spawn like `try_resume_run` does
   (reuse its normalization+spawn path). This is the ONLY documented redo path for `rejected`.
3. `migration-orchestrator/src/migration_control.py` (~39 + compact_status ~204-213): a run paused
   with a `rejected` step reports `status=paused, gate=null, next_actions=[]` — dead end for the
   LLM pilot. Fix: surface the rejected step as blocking gate + `next_actions=[rollback,jump,restart]`.
4. Minor: add `rejected` to frontend `StepStatus` union (`frontend/src/types.ts`) and to
   `routes/schema.py` (~96) step-states list (which already omits `halted` — decide intent).
   Add regression tests for 1+2 in `tests/test_gate_integrity.py` (same sync style).

## Exact resume steps

1. Fix the 4 items above (the stopped agent's full prompt is reusable — it contains all details).
2. `python3 -m pytest migration-orchestrator/tests/ -q` → must pass (12 + new regression tests).
3. Commit P0 ONLY (the files listed above + QUALITY-PLAN.md + this file), message like
   `feat(quality): P0 — env truth (.env.local), engine gate integrity (rejected state, plan lint, PROBE[NNN]), doc honesty`.
   Never commit `.env.local` (gitignored — verify with `git check-ignore .env.local`).
4. Update the execution log in QUALITY-PLAN.md §7, mark task #14 completed.
5. Proceed to P1 (tasks #15→18): artifact bridge + minimal passthrough (see QUALITY-PLAN §5 P1
   table — the recon details live in the P1 task descriptions #15-18). Key recon facts: the v1
   plans (`orchestration/plans/supercar-garage.plan.json`) already run scaffold→deploy→content
   headless with committed probes; sanctioned write path = MCP (`load_content.py`), NOT GraphQL;
   v2 manifest lacks `htmlFragment`/`needsFullPage`/`interactive`/instance→type map;
   scaffold needs a TTY (expect); no site exists on the instance (only systemsite).

## Standing items

- **Key rotation (Julian):** OVH/DeepSeek keys in `~/.config/opencode/opencode.jsonc` still to
  rotate (no hardcoded keys left in `orchestration/lib` — they read env/opencode.jsonc).
- Known engine gap (pre-existing, out of P0 scope): `jump_to_step` dependent-reset is story-scoped.
- P2 note: segmentation gate currently passes GREEN on total model failure — first P2 fix.
