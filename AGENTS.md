# AGENTS.md - jahiaMigration orchestration contract

You are an agent run by the **llm-orchestration-loop** against this repository.
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

**All content operations go through the Jahia MCP server, not GraphQL.** This is
non-negotiable. Creating, updating, moving, querying, translating, and publishing
nodes - use the MCP. Hand-crafted GraphQL mutations are a fallback you reach for
only when the MCP genuinely cannot do the operation, or the MCP server is
unavailable - and when you fall back, say so in your `summary`.

- The MCP server is at `$JAHIA_HOST/modules/mcp`. It exposes purpose-built tools
  (e.g. `content.create`, `content.type`, `page.structure`, publish tools).
- **Authentication:** the APIToken lives in `<project_path>/.env` as
  `JAHIA_MCP_TOKEN` (gitignored). Source the project `.env` first, then send it
  as an `Authorization: APIToken` header on every MCP call.
- Call it via JSON-RPC 2.0 over HTTP POST (Bash + curl), as documented in
  `.agents/skills/09-create-content/SKILL.md`:
  ```bash
  set -a; . "$project_path/.env"; set +a            # loads JAHIA_HOST + JAHIA_MCP_TOKEN
  curl -s -X POST "$JAHIA_HOST/modules/mcp" \
    -H "Content-Type: application/json" \
    -H "Authorization: APIToken $JAHIA_MCP_TOKEN" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
         "params":{"name":"TOOL_NAME","arguments":{ ... }}}'
  ```
- Check availability at the start of any content step:
  `bash orchestration/probes/mcp.sh <project_path>` (reads `JAHIA_MCP_TOKEN`
  from `.env`, prints version + tool count).
- For Claude Code sessions, the same server is registered in the repo-root
  `.mcp.json` (also gitignored) so MCP tools appear natively.
- **Images are content - import them into the DAM and reference them by
  WEAKREFERENCE, never a URL string.** This is non-negotiable (learned on
  sial-paris). Rules:
  1. **Capture** image URLs with a real browser (Chrome MCP) - the reference site
     blocks headless fetch (403), so the loop agent cannot discover them. Write a
     per-page source manifest `orchestration/images/<project>.json`.
  2. **Import** each image with the MCP tool **`media.upload.url`** (siteKey,
     sourceUrl=HTTPS, folder=existing, fileName). This creates ONE DAM node with a
     CONSISTENT UUID across default+live. Do NOT use the `import-image` servlet for
     referenced images - it creates DIFFERENT UUIDs per workspace, so weakreferences
     break in live and you fall back to a URL string (the bug we spent days on).
  3. **Reference** the node via the component's WEAKREFERENCE field
     (`image`/`backgroundImage`/`logo`/`photo`), set via
     `setValue(type: WEAKREFERENCE, value: <uuid>)`, then publish the node.
  4. **Never** populate the `*ExternalUrl` string fields (imageExternalUrl,
     backgroundImageUrl, logoExternalUrl). They are an anti-pattern: the image
     shows as a raw URL in Content Editor instead of a picked DAM asset. If one is
     already set, clear it after setting the weakreference.
  5. If an image already exists in the DAM with a consistent UUID, just reference
     it (no re-import). The harness tools `orchestration/images/import.py`,
     `set_hero_refs.py`, and `set_image_refs.py <project> <siteKey> <ns>` implement
     this end to end and are the canonical reference. The probe
     `orchestration/probes/no-url-images.sh` fails the step if any image field
     still holds a URL string. Full detail: `.agents/skills/09-create-content/SKILL.md`.
- Verification *reads* in probe scripts still use the live HTML render via curl -
  that is checking the result, not managing content, and is fine.

Why MCP over GraphQL: no hand-built query strings, i18n resolved automatically
from the `locale` argument, and fewer silent permission/Origin failures.

---

## 2b. Component reuse - map onto existing types, do not multiply them

Jahia integration pattern: **a content type is reused across many pages; page
variety comes from views, not new types.** When you discover a new page, you do
NOT create a component per section. You map each section onto an existing
`<ns>:` type. This module already ships a full component library.

Order of preference when fitting a discovered section:

1. **Reuse an existing type as-is.** Same fields → same type. Just place a node.
2. **Add a new view to an existing type.** Markup differs but the properties
   match → add `<variant>.server.tsx` next to `default.server.tsx` and select it
   with the node's view (e.g. `editorialBlock` already has `default`, `rightImg`,
   `verticalImage`; `newsArticle` has `default`, `card`, `fullPage`). No CND change.
3. **Extend an existing type** with an optional property only if a field is
   genuinely missing and the type is otherwise the right fit.
4. **Create a new type** - last resort. Only when no existing type's property
   shape fits. This is a deliberate decision: `STOP` and return `status: "halt"`
   describing the section and why nothing fits, so the operator approves it and
   the baseline is updated.

Before mapping, list the catalog:
`bash orchestration/probes/inventory.sh <project_path> <namespace>` - prints
every type and its existing views.

This is enforced. `orchestration/component-baseline.txt` is the approved type
set (41 types). The content step runs
`bash orchestration/probes/no-new-types.sh <project_path> <namespace> <baseline>`;
it fails if any type exists that is not in the baseline. New views never add a
type, so they pass. To legitimately add a type, the operator approves the halt
and the baseline is regenerated with `inventory.sh --write`.

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
   `orchestration/reference/<project>/` *before* modelling or creating content.
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
   - `fidelity.sh <reference_url> <live_url>` — every reference section heading is
     present locally and card/list counts aren't far below the reference (catches
     a whole section silently missing). Pass the **original URL** (the probe
     captures it); only pass a saved file when the original is bot-protected.
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

All under `orchestration/probes/`, run from repo root:

| Probe | Proves |
|-------|--------|
| `connect.sh <project_path>` | Jahia reachable + creds valid (HTTP 200/400) |
| `analyze.sh <project_path>` | `component-manifest.json` + `content-data.json` exist, non-empty |
| `build.sh <project_path>` | `yarn build` exits 0 |
| `assets.sh <project_path>` | `static/` has CSS and Layout references a stylesheet |
| `cnd.sh <project_path> <namespace>` | build clean + namespace in `definitions.cnd` + en/fr `.properties` |
| `component.sh <project_path> <name>` | named component source exists + build clean |
| `component-validate.sh <project_path> <ns> <ComponentDir> [page] [site] [lang]` | **FULL per-component gate** (see 5a) — source, **no duplicate default-view**, CND patterns (that component only), en+fr i18n for every type/property, build, deploy, bundle ACTIVE, and a **non-home page renders 200** (+ clean engine log) |
| `cnd-patterns.sh <project_path \| one.cnd> [ns]` | CND modelling rules (mix:title, jmix:tagged/categorized, linkTypeInitializer, weakref). Pass a single `.cnd` to lint just one component |
| `templates.sh <project_path>` | Layout has >=2 `AbsoluteArea` (header+footer) |
| `deploy.sh <project_path>` | build + `yarn jahia-deploy` succeed |
| `content.sh <project_path> <site> <lang> <page1,page2,...>` | each page's LIVE `<main>` text > 400 chars |
| `fidelity.sh <reference.mhtml\|html> <live_url> [min_pct]` | **ANTI-HALLUCINATION** — every reference section heading is present in the local render, and the card/list count isn't far below the reference. Proves "looks like the original" instead of claiming it |
| `artifact.sh <file> [forbidden_regex]` | output file exists (and lacks a forbidden pattern, e.g. `critical`) |

If a probe is wrong for a project, fix the probe script (it is versioned) rather
than skipping verification.

---

## 5a. Per-component gate — validate EACH component before moving on (MANDATORY)

Components are built and validated **one at a time**. You may **not** start, scaffold,
or add the next component until the current one passes its full gate. "I built five
components" is not a step; "component N passed `component-validate.sh`" is.

For **every** component you add or modify (CND, view, resource bundle, or its content),
the step is not `completed` until:

```
orchestration/probes/component-validate.sh <project_path> <namespace> <ComponentDir> [smoke_page] [site_key] [lang]
```

exits 0, and that exact command is in `commands_requested`. It runs the whole chain:
**source present → no duplicate default-view → CND patterns (that component) → en+fr
i18n for the type and every property → build → deploy → bundle ACTIVE → a non-home page
renders HTTP 200 → engine log free of `already exist`**.

Rules:
- One component, one gate, one pass — then proceed. A red gate halts the run; fix the
  component (not the probe, unless the probe is genuinely wrong) and re-run.
- **Always pass `<site_key>` (and a `<smoke_page>` that uses the component).** The render
  smoke is what catches a duplicate-view / registration crash — it makes every non-home
  page 404 while the home page still renders, so a home-only check gives a false pass.
- Never batch many components behind one deploy and a single glance. That is exactly how
  a duplicate `pagesPushesItem` view shipped and 404'd the whole site
  (`.agents/skills/11-debug` → "duplicate view registration"). One gate per component
  would have caught it on the spot.

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
