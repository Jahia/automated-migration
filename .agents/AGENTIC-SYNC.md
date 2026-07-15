# Sync with `@jahia/agentic` (upstream Jahia reference harness)

jahiaMigration's reference dev/integration skills (`.agents/skills/dev/`) track
the official [`Jahia/agentic`](https://github.com/Jahia/agentic) harness. The
numbered `00-13` skills are the migration **workflow**; `dev/` is the underlying
Jahia dev knowledge that mirrors agentic.

- **Last synced:** v0.5.1 (2026-07-15)
- **Re-sync:** `./.agents/agentic-sync.sh` → prints missing / changed / identical.

## Incorporated at v0.5.1 (2026-07-15)

Upstream renamed its review suite; `dev/` follows (mirrored from AIStartupKit's
reconciled v0.5.1 sync — its `jahia-review-code` keeps the richer local checks
C9–C12 + W10 that upstream lacks):

- `jahia-dev-review` → **`jahia-review-code`**, `jahia-dev-site-review` →
  **`jahia-review-site`**, plus new **`jahia-review`** umbrella (code + site
  review in parallel via subagents).
- `jahia-review-site` is upstream v0.5.1: full axe ruleset (ANY violation
  fails) + **Lighthouse SEO audits**; reads `pages-to-review.json`, writes
  `pages.json` only on pass. Includes our fix installing the `lighthouse`
  package upstream's Step 1 forgot.
- **Probe fork:** `orchestration/probes/site-review.sh` now runs a
  probe-owned copy of the v0.4.0 script (`orchestration/probes/site-review.mjs`)
  keeping the critical/serious gate — the v0.5.1 any-violation gate would block
  migrations that reproduce source markup 1:1. See the probe header.
- `check-cnd.mjs` gained AIStartupKit's enhancements (merged with our local
  adaptations, see below): `// cnd-check-ignore(<rule>): <reason>` suppression
  directive + name-scoped `missingI18n` keyword matching.
- Small fixes: `jahia-dev-properties` portable grep, `jahia-jcr-sql2` pointers
  (`jahia-cnd-author`, `jahia-dev-java`), `cnd-authoring-experience.md`
  underscore rule for `.properties` keys.
- Not applicable: v0.5.0 Antigravity/Kiro adapters + MCP-register-on-install
  (CLI installer features).

## Incorporated at v0.4.0 (into `.agents/skills/dev/`)

| Skill | Notes |
|---|---|
| `jahia-cnd-author` | `context: fork` CND modeling agent + 9 `references/cnd-*.md`. Step `04-define-content-types` should defer to it for non-trivial modeling. |
| `jahia-dev-review-cnd` | deterministic CND linter (`scripts/check-cnd.mjs`). **Wired as probe** `orchestration/probes/cnd-review.sh` — complements `cnd-patterns.sh`. |
| `jahia-dev-site-review` | axe-core a11y + SEO scoring (`scripts/review-pages.mjs`). **Wired as probe** `orchestration/probes/site-review.sh` — complements `render-truth.sh`. (Since v0.5.1: renamed `jahia-review-site`; the probe runs its own fork of the v0.4.0 script.) |
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
**we keep ours** — we are more advanced on those subjects. We do NOT fold the
smaller agentic versions (or their nuggets) back in; our versions lead.

### Local addition to `jahia-cnd-author/references/cnd-modeling-decisions.md`

Appended a **"Layout / rendering variation: property vs view vs new type"**
section: prefer a `choicelist` **layout property** (contributor flips it in
Content Editor) for per-instance toggles (image left/right, columns, colour),
a named **view** only for structurally different markup, a new **type** only for
a different field set. Mirrored into `01-analyze` Step 3b/4b and AGENTS §2b (1b).
Re-apply after re-sync.

### Local adaptation of `check-cnd.mjs`

`jahia-dev-review-cnd/scripts/check-cnd.mjs` is locally adapted: the
`weakrefNoConstraint` rule **exempts `startNode` and `excludeNodes`** — query-root
reference fields that legitimately point to arbitrary containers (our "full node
browser" convention) — and selector-constrained weakrefs (`category[...]`, file
pickers). All other weakrefs still require a `< type` constraint. Since the
v0.5.1 pass it ALSO carries AIStartupKit's ignore directive
(`// cnd-check-ignore(<rule>): <reason>` on the line above a property) and
name-scoped `missingI18n` matching (keywords tested against the property NAME,
with the color/font/theme config exemption preserved). When re-syncing from
upstream, re-apply all of these.

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
`migration-orchestrator` + probe gates are the implementation. The adoptable
delta was agentic's **quality gates** (CND linter, a11y/SEO scoring) — now wired
as probes. Re-check their plans when evolving the loop.
