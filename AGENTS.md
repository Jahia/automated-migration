# AGENTS.md - jahiaMigration orchestration contract

You are an agent run by the **migration-orchestrator** against this repository.
This file is your contract. The loop injects it into every step prompt and
expects you to follow it exactly. Read it fully before doing anything.

---

## 0. Runtime reality (read this first)

- You are **not** running inside Claude Code. **Slash commands do not exist
  here.** A prompt that says "run `/5-components`" means: open the matching
  `SKILL.md` file by path, read it, and follow its instructions yourself.
- The repository skills under `.agents/skills/<name>/SKILL.md` are **reference
  documents**, not executable commands. The step you are given tells you which
  one to read.
- Your final message must be **exactly one JSON object** (see section 4). The
  harness parses it. Anything else is ignored or breaks the run.

---

## 1. The repo is a harness; work happens inside one project

`repo_dir` is the harness root (`jahiaMigration/`). It holds many migration
projects. **Every run targets exactly one project**, given to you in the step
`INPUTS` as `project` and `project_path` (e.g. `projects/sial-paris`).

- The project folder **is** the Jahia JS module: `package.json`, `src/`,
  `settings/`, `static/`, `vite.config.mjs` all live directly under
  `project_path`.
- All build/deploy commands run **inside** the project:
  `cd <project_path> && yarn build` and `cd <project_path> && yarn jahia-deploy`.
- **Node >= 22 is required** (v22.21.0). The Vite plugin uses `styleText` from
  `node:util`; Node 18 fails the build with a cryptic error. The loop/opencode
  process must run under Node 22 (via `mise`/`nvm`) or every build, cnd,
  component, and deploy probe fails.
- Probe scripts (section 5) are invoked from the **repo root**, taking
  `<project_path>` as an argument. Do not `cd` before calling them.
- Never touch a different project's folder than the one in your INPUTS.

---

## 2. Credentials and environment

- Jahia connection lives in `<project_path>/.env`:
  `JAHIA_USER` (form `user:password`, default `root:root`) and `JAHIA_HOST`
  (default `http://localhost:8080`). `yarn jahia-deploy` reads it automatically.
- **Every GraphQL curl MUST include** `-H "Origin: $JAHIA_HOST"`. Without it
  Jahia returns `Permission denied` even with correct credentials.
- Writes go to the `default` workspace; live visitors read `live`. **Always
  publish after a mutation**, then verify against the `live` render.
- **Publish completeness** (a publish returning `true` ≠ visible on live):
  - i18n content (jcr:title, rich text, link targets) only reaches live when you
    publish **WITH** the language — `publish(languages:["<lang>"], publishSubNodes:true)`
    / MCP `"languages":["<lang>"]`. Omit it and EDIT updates while LIVE stays stale.
  - Publishing a page does NOT publish the DAM images / linked nodes / categories
    it references by weakreference — publish those too (`/sites/<site>/files`,
    `/sites/systemsite/categories`), or the reference resolves to null and the
    asset silently never renders.
  - Prove it with `bash orchestration/probes/publish-parity.sh <project_path> <site> <langs>`
    — fails on any weakref that doesn't resolve in LIVE or any translation
    present in EDIT but missing in LIVE.

---

## 2a. Content management - Jahia MCP server first, GraphQL only as fallback

**All content operations go through the Jahia MCP server** (`$JAHIA_HOST/modules/mcp`,
JSON-RPC 2.0; auth = `Authorization: APIToken $JAHIA_MCP_TOKEN` sourced from the
project `.env`). Hand-crafted GraphQL mutations only when the MCP genuinely cannot do
the operation - and say so in your `summary`. Availability check:
`bash orchestration/probes/mcp.sh <project_path>`.

**Images are content**: import into the DAM (once, into `default`, then publish the
file - same UUID in live) and reference by WEAKREFERENCE - **never a URL string**
(`no-url-images.sh` fails the step). Full transport, auth, and image-import contract
(incl. the WAF image-proxy and the UUID/workspace caveat):
`.agents/skills/09-create-content/SKILL.md` - and the focused sub-skills
`09a-populate-page` / `09b-populate-shell` for generated content stories.

---

## 2b. Component reuse - map onto existing types, do not multiply them

**A content type is reused across many pages; page variety comes from views, not new
types.** Preference order when fitting a discovered section: (1) reuse a type as-is;
(1b) add a per-instance layout property (choicelist) the view branches on; (2) add a
new view to an existing type; (3) extend a type with an optional property; (4) create
a new type - LAST resort: `halt` for operator approval, then regenerate the project
baseline. Enforced per project by `inventory.sh` (catalog + `--write` baseline),
`no-new-types.sh` (content may not introduce types), and `dup-shapes.sh` (no two types
share a property shape). Full doctrine + workflow:
`.agents/skills/04-define-content-types/SKILL.md`.

---

## 3. The hardening rule - a step is done only when its probe exits 0

The reason this migration was moved into the orchestration loop: agents wrote
`"status": "completed"` because they *believed* they had finished, while the
live instance disagreed. **You do not get to assert completion. You prove it.**

Mechanically:

1. Each step's `acceptance_criteria` contains one or more lines beginning with
   **`PROBE:`** followed by a command (usually `bash orchestration/probes/...`).
2. You **must** copy every `PROBE:` command, verbatim, into the
   `commands_requested` array of your JSON result.
3. The harness runs each command with `cwd` = repo root. The step passes only
   if **all of them exit 0**. If any fails, your step fails and is retried.
4. Do the actual work first (read the skill, edit files, build, deploy,
   publish). Only then echo the probes. Echoing a probe you have not satisfied
   just burns a retry.

Trust the probe, not your own summary. `in_progress`/`failed` honestly reported
is cheaper than a false `completed`.

---

## 3a. Anti-hallucination contract (the most important rule)

Hallucination here = **claiming something is done / verified / matches the
original without proof**. It is not acceptable. The operator should never have to
be your diff tool. Follow this every step:

1. **Get the reference YOURSELF before building — browser-first for dynamic
   sites.** Work from the page in front of you, **never from memory of what the
   site "probably" looks like**. For any site whose listings / facet values /
   article bodies / images load via JS, or that sits behind a WAF (Cloudflare),
   the **wget/curl cache is only the static shell** — the content that matters
   most is not in it. Use the **browser as the primary capture** (Chrome MCP:
   `navigate` + `get_page_text` + `javascript_tool`) per
   `.agents/skills/capture-reference/SKILL.md`, and save the captured truth to
   `projects/<project>/.reference/` *before* modelling or creating content.
   Fabricating summaries / titles / taxonomy / images from a partial cache is the
   #1 source of wrong content. A human-provided saved copy (MHTML / paste) is a
   last-resort fallback. When even the browser can't reach a page, **`halt` and
   ask the operator** — asking is correct; guessing is the hallucination to avoid.

2. **Prove, don't claim.** Every "done / verified / looks like the reference"
   statement must be backed by **probe output or a measured artifact** — a probe
   that exited 0, a `curl` body, a `getBoundingClientRect()` measurement, a
   screenshot. **Forcing one DOM element open, measuring one number, or your own
   narration is NOT verification.** If you didn't measure it, say "not verified".

3. **Run BOTH per-page gates — content fidelity AND render truth — AT EACH
   component/page creation, never as a final sweep.** As soon as a page is filled
   (or a component is placed on its page), render-gate THAT page before moving to
   the next; a defect caught on page 1 must not be discovered only after page 30.
   The content step's gate is `render-all.sh <project> <site> <lang> @sitemap`
   (loops `render-truth` over every page and fails on the first bad one); the
   deploy step render-gates the shell (`render-all ... /home`). A page is not done
   until both of these exit 0:
   - `fidelity.sh <reference_url> <live_url>` — cheap curl pass: every reference
     section heading is present locally and card/list counts aren't far below the
     reference (catches a whole section silently missing). **For JS-rendered
     content prefer `fidelity-live.sh <captured.html> <live_url>`** — it renders
     both sides in a real browser and diffs sections + card counts + **facet
     values**, against the persisted `.reference/captured/<slug>.html` (no WAF,
     no re-fetch). curl-`fidelity.sh` is the static fallback.
   - `render-truth.sh <live_url>` — loads the page in a headless browser, scrolls
     through it, and FAILS on render-only defects that counts/grep cannot see:
     broken images (`naturalWidth==0`), content stuck hidden (`opacity:0` after
     scroll = a scroll-reveal with no JS), collapsed shared regions (a header/
     footer at 0 height), and video sections with no working `<iframe>`/`<video>`
     player (`<video><source type="video/youtube">` never plays). It writes a
     screenshot artifact. Run it on a `/cms/editframe/...` URL with `--edit` to
     verify shared regions render in Page Builder too. **A passing build or a
     non-zero grep count is NOT a substitute for this gate.**

4. **Verify on the surface that actually tells the truth:**
   - Smoke-render a **non-home** page — home alone masks site-wide registration
     crashes (see 5a / `component-validate.sh`).
   - For screenshots below the fold, use the **browser's native scroll**, not
     `scrollTop`/`scrollIntoView` — these pages reset JS scroll, so a JS scroll +
     screenshot silently shows the top of the page and lies to you.
   - Before calling a node "missing" or "stray", cross-check the rendered DOM
     against the **authored JCR tree** (GraphQL `nodeByPath … children`). DOM
     artifacts (links rendered inside a component) are not authored nodes.

5. **Correct your own false claims out loud.** If a check disproves something you
   said, state it plainly in `summary` and fix it — do not quietly move on.

If you cannot prove a claim, the honest status is `in_progress` or `failed`, not
`completed`.

---

## 4. Required output - return exactly this JSON

```json
{
  "step_id": "<the step id you were given>",
  "agent": "code",
  "status": "completed | failed | halt",
  "summary": "what you actually did, with evidence (file paths, counts, probe output)",
  "modified_files": ["paths you created or changed"],
  "commands_requested": ["every PROBE: command from acceptance_criteria, verbatim"],
  "risks": ["anything the next step should know"],
  "loop_to": null
}
```

- `status: "halt"` - use at a **Human Gate** (section 6) or on a grave problem
  (data loss risk, unresolved ambiguity, corrupted state). The run pauses for a
  human. Put what needs deciding in `summary`.
- `loop_to` - a prior `step_id` to jump back to if this step proved an earlier
  step was wrong; otherwise `null`.

---

## 5. Probe scripts (the verification library)

All probes live under `orchestration/probes/`, run from the repo root. **Your step's
`PROBE:` lines are the contract**: run each exactly as written and include it in
`commands_requested`; the step passes only when every one exits 0. The full library
(what each probe proves, args, WARN-vs-FAIL semantics) is documented in
`orchestration/probes/README.md`. If a probe is wrong for a project, fix the probe
script (it is versioned) rather than skipping verification.

---

## 5a. Per-component gate — validate EACH component before moving on (MANDATORY)

Components are built and validated **one at a time** - "I built five components" is
not a step. Generated plans enforce this structurally: ONE story per component, gated
by `component-one.sh` (source + no-stub + i18n + cm view, by nodeType), with the
module-wide `components-all.sh` + build as the closing gate.
`component-validate.sh <project_path> <ns> <ComponentDir> [smoke_page] [site] [lang]`
remains the deep post-deploy gate (build -> deploy -> bundle ACTIVE -> a NON-home page
renders 200) for iterating on a single deployed component. Never batch many components
behind one deploy: a single duplicate default-view registration 404s the whole site
(see `.agents/skills/11-debug`).

---

## 6. Human validation gates

Some steps are checkpoints where a human must look before the run continues.
The step says so and lists what to present. At those steps: finish the work,
satisfy the probe, then return `status: "halt"` with the evidence to review in
`summary`. The operator resumes the run after validating.

Gates: (1) component scope after analysis, (2) namespace after scaffold,
(3) shell layout after templates, (4) visual fidelity after content,
(5) review sign-off. Source: `_references/human-validation-gates.md`.

---

## 7. Non-negotiable rules (apply to every step)

**All tracks**
1. Never escalate to a system JCR session for content the calling user authored.
2. All content operations use the **Jahia MCP server** (section 2a); GraphQL is
   a fallback only. Always publish after a mutation; verify on `live`.
3. When you do fall back to GraphQL curl, always include `-H "Origin: $JAHIA_HOST"`.
4. Every module ships EN and FR at minimum.

**JS template set**
5. Never run `yarn dev`. Use `yarn build && yarn jahia-deploy`.
6. Never hardcode UI strings in views - use `t("key")` from `useTranslation()`.
7. Never hardcode links or URLs. All navigable links come from contributed content.
8. Only `jmix:hiddenType` on singleton layout types (header/footer). Never on
   child node types - it blocks Page Builder inline editing.
9. Never declare `j:linknode` or `j:url` in a CND - Jahia injects them via
   `linkTypeInitializer`.
10. Never declare `jcr:title` in a CND - inherit it via `mix:title` supertype.
11. Any mixin storing hidden child nodes must declare `+ childName (Type) = Type version`.
12. Keep all locale JSON files in sync (`en.json`, `fr.json`, ...). A key in one
    but missing in another renders as the raw key.

**Migration-specific**
13. Navigation goes 3 levels deep via a Jahia Navigation Menu component
    (`getChildNodes` on home for L1, recurse for L2/L3). Never hardcoded `<a>` lists.
14. Use `j:linkType (string, choicelist[linkTypeInitializer])` for every
    contributor-facing link. Never a plain string URL field.
15. Never create CND properties for tags or categories. Use `jmix:tagged`
    (free-form tags) and `(weakreference, category[autoSelectParent=false]) multiple`
    (taxonomy).
16. Every migrated module ships a JCRQuery and a GridRow component in its namespace.
16a. **Reuse components, do not multiply them** (section 2b). Map a discovered
    section onto an existing type; add a view if markup differs but properties
    match; create a new type only via an approved halt. New types beyond
    `component-baseline.txt` fail the content step.
17. Extract shared property groups into module mixins early (`nsmix:cta`,
    `nsmix:media`, `nsmix:badge`, `nsmix:seo`).
18. Every resource-bundle field key has a companion `ui.tooltip` key.
19. Every visible string is a contributor-editable, i18n CND field, null-guarded
    in the view. No hardcoded labels.
20. Accessibility is mandatory: every component passes WCAG 2.1 AA
    (`.agents/skills/dev/jahia-dev-accessibility`). Fix all critical/serious axe
    violations before a step is done.

---

## 8. Reading order for any step

1. This file (AGENTS.md).
2. `CLAUDE.md` - canonical orientation, only if you need deeper platform context.
3. The `SKILL.md` named in your step INPUTS (`skill` key), under `.agents/skills/`.
4. Relevant context docs in `.agents/context/` when the skill points to them.

Then: do the work, build, deploy, publish, satisfy the probe, return the JSON.
