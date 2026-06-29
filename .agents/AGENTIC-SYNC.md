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

## dev/ now mirrors ALL 18 agentic skills ("most complete")

`create-view`, `create-page-template`, `debug`, `review` were added so `dev/` is
the complete, agnostic Jahia dev-knowledge reference. The numbered migration
skills (`07-implement-components`, `08-page-templates`, `11-debug`, `10-review`,
`support-create-view`) remain the migration **workflow** — they reference `dev/`.
Where jahiaMigration's `dev/` version is bigger/better (accessibility,
query-content, import-from, build-component, create-template-set, start-local),
we keep ours. Agentic nuggets still to fold into ours next pass: the
`@jahia-cnd-author` sub-agent invocation (build-component) and the MCP
`site.create`/`site.list` flow (create-template-set, start-local).

## Reviewer + gates (added after the supercar "fiasco")

- **`.claude/agents/jahia-reviewer.md`** — adversarial reviewer agent: runs every
  gate probe + reviews faithful-DOM/editability/content-fidelity/i18n, writes
  `REVIEW.md`, APPROVE only when all green. Wired into the review step.
- **`orchestration/probes/no-stub.sh`** — fails on stub/placeholder/null-only
  views + viewless CND types. Wired into the components step + the review step.

## Convergence to watch (orchestration)

agentic's `docs/superpowers/plans/2026-06-25-agentic-harness-orchestration.md`
describes the SAME architecture jahiaMigration already runs: a lean orchestrator
driving a dev-worker / reviewer loop via small status files (`PLAN.md`,
`DEV_STATUS.md`, `REVIEW.md`), so the orchestrator never reads source. Our
`llm-orchestration-loop` + probe gates are the implementation. The adoptable
delta was agentic's **quality gates** (CND linter, a11y/SEO scoring) — now wired
as probes. Re-check their plans when evolving the loop.
