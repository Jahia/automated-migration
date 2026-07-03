# Orchestration - running jahiaMigration through the migration-orchestrator

This directory wires the jahiaMigration harness into the
[`migration-orchestrator`](../migration-orchestrator) so that migrations run
under a hardened, proof-driven engine instead of the in-repo `/migration-workflow`
Conductor (which depended on the LLM choosing to respect it).

> **Operator runbook:** to actually start the engine, author a plan from the
> template, launch a run and answer its human gates, follow
> [`.agents/skills/run-orchestration-loop/SKILL.md`](../.agents/skills/run-orchestration-loop/SKILL.md).
> Engine setup, plan schema, and REST API are documented in the engine's own
> [`README.md`](../migration-orchestrator/README.md). **The engine listens on
> port 8001** (matches `run.sh`'s `ORCH_URL`).

> **Quality & reliability plan:** the roadmap, phases and **pre-registered
> thresholds** governing the v2 pipeline live in
> [`QUALITY-PLAN.md`](QUALITY-PLAN.md).

## Why this exists

The loop's verifier runs whatever shell commands a step's agent returns in
`commands_requested` (with `cwd` = this repo's root) and **a step only passes
when every command exits 0**. We exploit that: each step carries a `PROBE:`
line in its `acceptance_criteria`, the agent is required (by `AGENTS.md`) to
echo that probe back, and the harness runs it. Completion is proven by a
command, not asserted by the model. That is the hardening.

> **Verifiable analyze pipeline (v2) — start here:** the reworked component &
> template identification (deterministic extraction → one bounded DeepSeek grouping
> step → deterministic assemble + gates → **reconstruction fidelity gate**) is
> documented in **[`ANALYZE-PIPELINE.md`](ANALYZE-PIPELINE.md)**. New tools in `lib/`:
> `semantic_extract.py`, `group_llm.py`, `assemble_manifest.py`, `stability_gate.py`,
> `cnd_emit.py`, `coverage_probe.mjs`, `reconstruct_probe.mjs`; plus `run_local.py`
> (deterministic plan executor) and `plans/acquia-analyze.plan.json`. Orchestrator UX
> specialization: [`../migration-orchestrator/frontend/MIGRATION_PROFILE.md`](../migration-orchestrator/frontend/MIGRATION_PROFILE.md).

## What's here

```
orchestration/
├── README.md              # this file
├── run.sh                 # submit + start + watch a plan against the loop
├── plan-template.json     # parameterized template for a new project
├── plans/
│   └── sial-paris.plan.json   # concrete, runnable plan for the SIAL Paris site
├── lib/
│   ├── cached-fetch.sh   # reference scraping: cache-to-disk + WAF/rate-limit backoff (see below)
│   └── tokenize-css.py   # variabilize imported CSS into a :root theme-token layer (see below)
└── probes/                # the verification library (the hard gate)
    ├── _lib.sh            # shared env loading
    ├── css-tokens.sh     # CSS is tokenized + site-theme mixin + Layout override wiring present
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
    ├── fidelity-all.sh    # FIDELITY GATE (wired): loops fidelity-live over @sitemap, each page vs its captured reference DOM; the gate in step_visual_diff + reviewer
    ├── fidelity-live.sh   # JS-rendered diff (sections+cards+facets) for ONE page vs captured .reference/captured/<slug>.html; called by fidelity-all
    ├── fidelity.sh        # DEPRECATED (curl/static, headings-only) — superseded by fidelity-all/-live; no-browser fallback only
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

### Reference scraping is cached and WAF-aware

Reference sites sit behind CDNs/WAFs (Cloudflare, Akamai) and the operator may be
on a VPN the WAF distrusts. `orchestration/lib/cached-fetch.sh` enforces two rules
for every fetch (skills 01/03/09 call it instead of bare `wget`/`curl`):

- **Always check the cache before scraping again.** Every scrape path — `curl`,
  recursive crawl, and the browser fallback — checks the cache first; a hit is
  reused with no network call. Pages/assets live under `<project>/.reference/cache/`
  (in-project, durable — survives sessions, context compaction, re-runs). A
  completed crawl is reused, not repeated. `FORCE_REFETCH=1` is the deliberate bypass.
- **Slow down when blocked.** A polite base delay (`RATE_DELAY`, default 2s) sits
  between requests; on any WAF/rate-limit signal (HTTP 403/429/5xx/520-524 or a
  Cloudflare challenge body) it backs off exponentially with jitter and raises the
  run-wide delay. After `MAX_ATTEMPTS` it returns exit code 2 and tells the caller
  to fall back to **browser capture** (Chrome MCP `get_page_text`) — never hammer.

```bash
FETCH=orchestration/lib/cached-fetch.sh
"$FETCH" get   projects/sial-paris "$URL"   # cache check, no network (exit 0=hit+path, 3=miss) — call before scraping
"$FETCH" fetch projects/sial-paris "$URL"   # cache-first fetch; network only on miss; backs off on WAF
"$FETCH" crawl projects/sial-paris "$URL" 3 # cache-first recursive crawl (skips a completed crawl)
printf '%s' "$browser_text" | "$FETCH" put projects/sial-paris "$URL"   # persist a browser-captured page
"$FETCH" cache-root projects/sial-paris     # -> .reference/cache
# RATE_DELAY=8 MAX_ATTEMPTS=8 (throttle harder) · FORCE_REFETCH=1 (bypass cache)
```

### CSS is tokenized for whole-site re-theming

Imported CSS is never left with hardcoded colors/fonts. `orchestration/lib/tokenize-css.py`
hoists every color and font-family literal into CSS custom properties on `:root`
(written to `static/css/theme-tokens.css`) and rewrites all usages to `var(--token)`.
Re-theming then needs no code redeploy — override the `:root` tokens via either path,
wired in `Layout.tsx` and gated by `probes/css-tokens.sh`:

- **Site-node theme mixin** (`<ns>Mix:siteTheme`, added to `/sites/<siteKey>`): editor
  sets `themePrimaryColor`, `themeFontHeading`, … → Layout emits an inline `:root{}`
  override.
- **Uploaded override stylesheet** (`themeOverrideCss` weakreference → a `.css` in the
  DAM): Layout links it **last** so its rules win the cascade.

```bash
python3 orchestration/lib/tokenize-css.py --out projects/sial-paris/static/css/theme-tokens.css \
  --report workflow-output/theme-tokens.md projects/sial-paris/static/css/*.css
bash orchestration/probes/css-tokens.sh projects/sial-paris
```

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

Plus, at the repo root: [`../AGENTS.md`](../AGENTS.md) - the contract the orchestrator
injects into every step prompt. The orchestrator reads `<repo_dir>/AGENTS.md`, so it
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

Prerequisites: `opencode` is installed, Node >= 22 (`mise`/`nvm`), and a local Jahia is up
at the `JAHIA_HOST` in `projects/<project>/.env`.

```bash
# 1. Start the migration orchestrator
cd migration-orchestrator
source .venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8001   # auto-spawns `opencode serve`

# 2. From this repo, submit + start + watch a plan
cd -                                              # back to jahiaMigration root
ORCH_URL=http://localhost:8001 \
  bash orchestration/run.sh orchestration/plans/<project>.plan.json --watch
```

`run.sh` POSTs the plan to `/runs`, starts it, and streams the event log. The
web UI is at `http://localhost:8001/app` (must be built first: `cd migration-orchestrator/frontend && npm install && npm run build`).

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
