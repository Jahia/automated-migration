# Sync with `@jahia/agentic` (upstream Jahia reference harness)

jahiaMigration's reference dev/integration skills (`.agents/skills/dev/`) track
the official [`Jahia/agentic`](https://github.com/Jahia/agentic) harness. The
numbered `00-13` skills are the migration **workflow**; `dev/` is the underlying
Jahia dev knowledge that mirrors agentic.

- **Last synced:** v0.4.0 (2026-06-29)
- **Re-sync:** `./.agents/agentic-sync.sh` → prints missing / changed / identical.

## Incorporated at v0.4.0 (into `.agents/skills/dev/`)

| Skill | Notes |
|---|---|
| `jahia-cnd-author` | `context: fork` CND modeling agent + 9 `references/cnd-*.md`. Step `04-define-content-types` should defer to it for non-trivial modeling. |
| `jahia-dev-review-cnd` | deterministic CND linter (`scripts/check-cnd.mjs`). **Wired as probe** `orchestration/probes/cnd-review.sh` — complements `cnd-patterns.sh`. |
| `jahia-dev-site-review` | axe-core a11y + SEO scoring (`scripts/review-pages.mjs`). **Wired as probe** `orchestration/probes/site-review.sh` — complements `render-truth.sh`. |
| `jahia-jcr-sql2` | focused JCR-SQL2 reference (complements `06-implement-jcr-query`). |

Adopted conventions (in `AGENTS.md`): load CND refs / use `jahia-cnd-author`
before writing CND · TypeScript LSP for API discovery · MCP-first · run
site-review after deploy.

## CHANGED — diverged, reconcile next pass (we mostly lead)

`jahia-dev-accessibility` (271 vs 11 — ours), `jahia-dev-query-content` (433 vs
204 — ours), `jahia-dev-import-from` (302 vs 244 — ours), `build-component`,
`create-template-set`, `start-local` (small diffs).

## Intentionally NOT mirrored into dev/

`create-view`, `create-page-template`, `debug`, `review` — jahiaMigration's
numbered migration skills (`07-implement-components`, `08-page-templates`,
`11-debug`, `10-review`, `support-create-view`) are the local, migration-tuned
equivalents.

## Convergence to watch (orchestration)

agentic's `docs/superpowers/plans/2026-06-25-agentic-harness-orchestration.md`
describes the SAME architecture jahiaMigration already runs: a lean orchestrator
driving a dev-worker / reviewer loop via small status files (`PLAN.md`,
`DEV_STATUS.md`, `REVIEW.md`), so the orchestrator never reads source. Our
`llm-orchestration-loop` + probe gates are the implementation. The adoptable
delta was agentic's **quality gates** (CND linter, a11y/SEO scoring) — now wired
as probes. Re-check their plans when evolving the loop.
