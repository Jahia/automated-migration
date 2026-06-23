# Orchestration - running jahiaMigration through the llm-orchestration-loop

This directory wires the jahiaMigration harness into the
[`llm-orchestration-loop`](../../llm-orchestration-loop) so that migrations run
under a hardened, proof-driven engine instead of the in-repo `/migration-workflow`
Conductor (which depended on the LLM choosing to respect it).

## Why this exists

The loop's verifier runs whatever shell commands a step's agent returns in
`commands_requested` (with `cwd` = this repo's root) and **a step only passes
when every command exits 0**. We exploit that: each step carries a `PROBE:`
line in its `acceptance_criteria`, the agent is required (by `AGENTS.md`) to
echo that probe back, and the harness runs it. Completion is proven by a
command, not asserted by the model. That is the hardening.

## What's here

```
orchestration/
├── README.md              # this file
├── run.sh                 # submit + start + watch a plan against the loop
├── plan-template.json     # parameterized template for a new project
├── plans/
│   └── sial-paris.plan.json   # concrete, runnable plan for the SIAL Paris site
└── probes/                # the verification library (the hard gate)
    ├── _lib.sh            # shared env loading
    ├── connect.sh         # Gate 0: Jahia reachable + creds
    ├── analyze.sh         # manifest + content-data exist
    ├── build.sh           # yarn build exits 0
    ├── assets.sh          # static/ has CSS, Layout references it
    ├── cnd.sh             # build + namespace in definitions.cnd + en/fr props
    ├── component.sh       # a named component source exists + build
    ├── component-validate.sh # FULL per-component gate: no-dup-view + cnd + i18n + build + deploy + non-home render (one component must pass before the next is started)
    ├── templates.sh       # Layout has header+footer AbsoluteArea
    ├── deploy.sh          # build + yarn jahia-deploy
    ├── content.sh         # every page's LIVE <main> text > 400 chars (accepts @sitemap)
    ├── fidelity.sh        # ANTI-HALLUCINATION: reference (mhtml/html) vs local render — every reference section heading present + card counts not far below; proves "looks like the original"
    ├── mcp.sh             # Jahia MCP server up with >=1 tool
    ├── inventory.sh       # list the module's content types + views (reuse catalog)
    ├── no-new-types.sh    # reuse guard: fail if a type appears outside the baseline
    └── artifact.sh        # an output file exists (and lacks a forbidden pattern)
```

Two reuse artifacts back `no-new-types.sh`:
- `orchestration/component-baseline.txt` - the approved `sialp:` type set (41).
- `orchestration/sitemaps/sial-paris.txt` - the target page tree (31 pages).

### Reuse, don't multiply components

The Jahia pattern is one content type reused across many pages, with variety
coming from **views**, not new types. Page discovery maps each section onto an
existing type; markup differences become an extra `*.server.tsx` view; a new
type is a last resort that requires an operator-approved halt. The content step
enforces this with `no-new-types.sh` against the baseline. To approve a new type,
regenerate the baseline: `bash orchestration/probes/inventory.sh projects/sial-paris sialp --write orchestration/component-baseline.txt`.

### Content management goes through the Jahia MCP server

All content operations (create/update/move/translate/publish) use the **Jahia
MCP server** at `$JAHIA_HOST/modules/mcp` via JSON-RPC curl, not GraphQL
mutations - enforced in `AGENTS.md` section 2a and in the content step itself.
The content step carries two blocking probes: `mcp.sh` (the MCP server is up)
and `content.sh` (the pages actually rendered). GraphQL stays available as a
documented fallback for operations the MCP cannot perform; if a run truly needs
that fallback, drop the `mcp.sh` probe line from that one step. Probe scripts
themselves read the live render with curl for verification - that is checking a
result, not managing content.

Plus, at the repo root: [`../AGENTS.md`](../AGENTS.md) - the contract the loop
injects into every step prompt. The loop reads `<repo_dir>/AGENTS.md`, so it
must live at the harness root.

## The plan model

`repo_dir` is this repo's root. Each run targets **one** project under
`projects/<name>/` (that folder *is* the Jahia JS module). The 13 migration
steps map to 6 epics:

| Epic | Steps covered | Probe-enforced gate |
|------|---------------|---------------------|
| foundation | connect, analyze | server reachable; manifest exists |
| scaffold_assets | scaffold, assets | build clean; assets present |
| content_model | content-types, navigation, JCRQuery, GridRow | cnd + components build |
| components_templates | components, templates, deploy | build; AbsoluteAreas; deploy |
| content_quality | content, review, accessibility | live `<main>` > 400; reports |
| fidelity_golive | visual-diff, vanity-urls | SUMMARY.md; redirect map |

Human validation gates (1-5 from `_references/human-validation-gates.md`) are
preserved: the relevant steps tell the agent to return `status: "halt"` after
the probe passes, pausing the run for operator review before it continues.

## Run it

Prerequisites: the loop is checked out at `../../llm-orchestration-loop`,
`opencode` is installed, Node >= 22 (`mise`/`nvm`), and a local Jahia is up at
the `JAHIA_HOST` in `projects/sial-paris/.env`.

```bash
# 1. Start the orchestration loop (in the loop repo)
cd ../../llm-orchestration-loop
source .venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8001   # auto-spawns `opencode serve`

# 2. From this repo, submit + start + watch the SIAL Paris plan
cd -                                              # back to jahiaMigration
ORCH_URL=http://localhost:8001 \
  bash orchestration/run.sh orchestration/plans/sial-paris.plan.json --watch
```

`run.sh` POSTs the plan to `/runs`, starts it, and streams the event log. The
web UI is at `http://localhost:8001/app`.

> Port note: `src/config.py` in the loop defaults to `8001`; its `.env.example`
> shows `8000`. Match `ORCH_URL` to whatever you pass to `uvicorn --port`.

## Add a new project

1. Scaffold/keep the module under `projects/<name>/` with its own `.env`
   (`JAHIA_USER`, `JAHIA_HOST`, and `JAHIA_MCP_TOKEN` for the MCP server).
   The `.env` is gitignored - never commit the token.
2. `cp orchestration/plan-template.json orchestration/plans/<name>.plan.json`.
3. Replace every `__PLACEHOLDER__` (`__PROJECT__`, `__SITE_URL__`,
   `__NAMESPACE__`, `__MIX_NAMESPACE__`, `__SITE_KEY__`, `__LANG__`, `__PAGES__`,
   `__REPO_ABS_PATH__`). Keep the `PROBE:` lines verbatim.
4. `bash orchestration/run.sh orchestration/plans/<name>.plan.json --watch`.

`AGENTS.md` and the probe scripts are project-agnostic - they take
`project_path` as an argument - so nothing else needs changing.

## Migrating off the in-repo Conductor

`/migration-workflow` and its per-step `SKILL.md` files stay as the **domain
reference** the agents read (their `inputs.skill` points at them). What moves
into the loop is the *control flow and verification*: step ordering, retries,
epic review, and the probe gate. `state.json` is superseded by the loop's run
state (SQLite + SSE) as the source of truth for progress.
