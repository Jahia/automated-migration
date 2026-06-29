# Harness improvements backlog

Distilled from the supercar-garage migration retro. The through-line of every
friction point: **the harness trusted "it ran" instead of proving "it looks
right, in the right workspace, against the real source."**

## Root-cause patterns observed

1. **Verification was inferential, not observational** — "done" was claimed from
   build success and grep/element counts. Render-only defects slipped through:
   scroll-reveal `opacity:0`, transparent/0-height header, dark-on-dark text,
   15px logos, missing video iframe, broken submenu, unstyled footer.
2. **Built from cache/assumptions, not the source of truth** — the reference
   listing, facet values, article bodies and image URLs load via JS behind a
   WAF; the wget cache had only partial static HTML. Result: fabricated
   summaries, wrong titles, wrong images, a missing 5th article — until the
   live site was consulted via the browser (the available WAF fallback).
3. **Invented markup instead of transcribing the reference DOM** — imported
   theme CSS is tightly coupled to exact structure (`grid-template-areas`,
   `#header`/`#footer` scoping, swiffy classes, `.slide-in` reveal). Custom
   markup → CSS silently doesn't apply → "totally off".
4. **"Published" ≠ visible** — content published while DAM images weren't; i18n
   content published without `languages:[fr]` → stale on live; AbsoluteAreas
   blank in Page Builder for lack of children. Observable only by querying LIVE
   / loading the edit frame — nothing gated it.
5. **The loop stubs big steps; gates were build-only** — 29/32 views stubbed,
   build still passed.

## Probes (highest leverage — make observable truth a hard gate)

- [x] **render-truth.sh `<url>`** *(DONE — wired as a per-page gate in AGENTS.md
  rule 3 + skill 12-visual-diff; `render-truth.mjs` does the checks)* — headless browser per
  page; FAIL on: text/image element computing `opacity:0` or 0 height after a
  full scroll, `<img>` with `naturalWidth==0`, a video section with no
  `<iframe>`/`<video>`, a collapsed shared region; WARN on low contrast. Saves a
  screenshot artifact. Catches: reveal, transparent/0-height header, broken/tiny
  images, missing video, dark-on-dark.
- [x] **publish-parity.sh** *(DONE — wired into the content step + AGENTS publish-completeness rule)* — every weakreference (images, linknodes) and every
  i18n property on published content resolves in **LIVE** for each language.
  Catches: unpublished DAM, the `languages:[fr]` gap, stubborn 404 files.
- [x] **edit-frame.sh `<page>`** *(DONE — wired into content step; verified PASS on supercar home)* — load `/cms/editframe/...`; each shared region
  (header/nav/footer) and each listing renders non-empty AND shows editable
  markers. Catches: AbsoluteArea-needs-children, blank footer in Page Builder.
- [x] **fidelity-live.sh** *(DONE — JS-rendered diff vs captured DOM; verified)* — diff against the **live** reference via browser
  (not cache): section order, card/item counts, facet values. Replaces the weak
  `fidelity.sh` (headings-only — passed visually-wrong pages).
- [ ] **no-stub.sh** — every CND type has a non-trivial view (LOC/AST threshold,
  not just a present file), a resource-bundle label+tooltip, and an icon; every
  registered component renders without throwing.
- [ ] **theme-coupling.sh** — scan imported CSS for `:not(.x){opacity:0}` reveal
  patterns (assert a reveal observer exists) and orphan SXA `facet`/`search`
  markup with no backing listing.

## Skills

- [x] **New `capture-reference` (browser-first)** *(DONE — skill + wired into analyze step + AGENTS rule 1 + 01-analyze pointer)* — for JS/WAF sites, Chrome MCP
  is the *primary* capture: snapshot every page's rendered DOM, real text
  (`get_page_text`), image URLs, and taxonomy/facet values to disk BEFORE
  modeling. Demote wget-cache to "static fallback".
- [ ] **Consolidate** the ad-hoc lessons added during this migration into
  coherent sections (header/footer transcription incl. `#header`/`#footer`
  scoping + grid-areas; theme-JS dependencies = reveal observer + carousel init;
  facet→category pattern; `jmix:mainResource` + jcrQuery listings; publish
  discipline = assets + all languages; editability = AbsoluteArea children +
  `RenderChildren`).
- [ ] **Observable "Definition of Done"** on every production skill: renders in
  live AND edit frame, images load, published in all languages, matches the
  reference screenshot — each line a command, not a vibe.

## Orchestration

- [ ] Swap build-only gates for the probes above as HARD per-step gates (a
  step's `PROBE:` asserts render-truth + publish-parity, not "build succeeded").
- [x] Decompose heavy steps (asset import, view implementation, content) into
  per-artifact units with per-artifact gates, so a stubbed 29/32 fails at once.
  *(DONE — `components-all.sh`: loops every component, FAILS naming any stubbed /
  viewless / unlabelled one, builds once. The loop engine (`run.sh` → external
  port 8001, static plan) can't fan out a dynamic step per discovered component
  without an engine change, so the within-repo fix is this batch per-component
  gate + the §5a mandate to validate one component at a time via
  `component-validate.sh`. Wired into `step_components` in plan-template + supercar
  plan, the reviewer agent, and skill 07.)*
- [x] **Render gate runs at EACH page/shell creation, not a final sweep** —
  `render-all.sh` loops `render-truth` over every page; wired into the DEPLOY
  step (shell `/home`) and the CONTENT step (`@sitemap`, per page) in
  plan-template + supercar plan; AGENTS rule 3 + skill 09 DoD updated.
- [x] Per-page sign-off gate: also add fidelity-live + publish-parity to the
  per-page loop. *(DONE — `fidelity-all.sh` loops `fidelity-live` over `@sitemap`
  (each page vs its captured reference DOM), wired into `step_visual_diff` +
  the reviewer; `publish-parity.sh` is in the content step. `render-truth` per
  page via `render-all`. fidelity-all FAILs if no page was captured, so it can't
  pass on an empty capture.)*
- [ ] Human visual checkpoints at milestones (after layout, after content), not
  only at the end.
- [ ] Final **completeness-critic** pass: "does every declared artifact exist
  and render?" — contains the loop's stubbing.

## Anti-hallucination contract (top-level AGENTS.md) — each backed by a probe

1. **Observational proof** — never report done from build/grep; attach the
   observed artifact (screenshot / LIVE query / edit-frame).
2. **Source of truth** — never fabricate content/titles/taxonomy/images; capture
   from the live source via the browser; if unavailable, STOP and ask.
3. **Faithful DOM** — transcribe reference component markup 1:1 when imported
   theme CSS is in play.
4. **Publish completeness** — after any content change, publish referenced
   assets + all languages, then verify in LIVE.

## Implementation order

1. ~~`render-truth.sh` + wire as a gate~~ ✅ **done** (probe + `.mjs`, gated in
   AGENTS.md rule 3 + skill 12; verified: catches broken img / hidden / collapsed
   / playerless-video on a fixture, passes the fixed supercar pages)
2. ~~render gate at EACH page/shell creation~~ ✅ **done** (`render-all.sh` in the
   deploy + content steps)
3. ~~`publish-parity.sh` + the `languages:[…]` publish rule~~ ✅ **done** (probe +
   wired into content step; verified PASS on supercar: 22 weakrefs, 0 broken)
4. ~~browser-first `capture-reference` skill~~ ✅ **done**
5. ~~`edit-frame.sh`~~ ✅ **done**
6. ~~`no-stub.sh` gate~~ ✅ **done** (wired into components + review steps)
7. ~~agentic v0.4.0 sync~~ ✅ **done** — dev/ mirrors all 18 skills; cnd-author,
   review-cnd→`cnd-review.sh`, site-review→`site-review.sh`, jcr-sql2; reviewer
   agent; conventions; `.agents/agentic-sync.sh` + `AGENTIC-SYNC.md` (both repos)
8. ~~analysis review~~ ✅ **done** — data-shape clustering (not markup),
   `dup-shapes.sh` reuse/views gate, per-project agnostic `no-new-types` baseline,
   browser-first + scrape-completeness, image-proxy for distant images,
   layout-property (property>view>type) modeling lever
9. ~~`fidelity-live.sh`~~ ✅ **done** — JS-rendered diff (sections+cards+facets) vs the captured reference DOM; reviewer + AGENTS rule 3 use it
10. ~~decompose loop heavy steps into **per-artifact** units so a stub fails at once~~
    ✅ **done** — `components-all.sh` per-component completeness gate (loops every
    component, names any stub/viewless/unlabelled one, builds once); wired into
    `step_components`, the reviewer, and skill 07. Verified: PASS on supercar (32
    components), FAILS naming a stub/viewless/missing-i18n fixture. Same i18n
    `j:*`/query-root exemption applied to `component-validate.sh` so the two agree.
11. (open, your call) AIStartupKit branch `agentic-sync-0.4.0` — push done, PR/merge?

## Deploy-blocker findings (lesalondelaphoto, 2026-06-29) — the gates miss real install failures

The module built clean and passed `cnd.sh` + `cnd-review.sh`, yet was **undeployable**.
The Docker logs (`jcontent-8230:/usr/local/tomcat/logs/jahia.log`) revealed a CHAIN of
**5 distinct CND/packaging faults**, each hidden behind a generic
`InstallModule: Cannot install package.tgz = java.io.IOException`, then an OSGi
`BundleException`. None were caught by the existing probes:

1. **Missing namespace declarations** — a hand-built `definitions.cnd` lacked
   `jcr`/`nt`/`mix`/`j`; `mix:title` as a *supertype* couldn't resolve. (The real
   `npm init @jahia/module` scaffold includes the full header; our deterministic
   scaffold must too.)
2. **Self-referencing nodetype mixin** — declaring `<ns>mix:queryContent` AND
   extending/referencing it = a `Require-Capability` on a type the bundle provides
   → install fails. Use the built-in `jmix:mainResource`; `JcrQuery` `subnodetypes`
   targets `jmix:mainResource`. (supercar's CND already documents this.)
3. **Duplicate type definition** — `lsp:ctaButton` declared in both
   `definitions.cnd` and a component dir → CND reader throws. (The skill-07 dedup
   step the agent skipped.)
4. **Choicelist property order** — `(string, choicelist) < 'a','b' = 'x'`
   (constraints before default) is rejected; correct order is
   `= 'x' autocreated < 'a','b'`.
5. **Whitespace in a `subnodetypes` CSV** — `'jnt:page, jmix:mainResource'` (space
   after comma) generated `Require-Capability (nodetypes= jmix:mainResource)` with a
   leading space → never matches the provider → OSGi resolution fails. Must be
   `'jnt:page,jmix:mainResource'` (no spaces).

- [ ] **`cnd-deploy.sh` gate (HIGH VALUE)** — the cnd probes check antipatterns +
  `yarn build`, but NEVER exercise Jahia's install-time CND parse + OSGi resolution.
  Add a gate that actually deploys and asserts the bundle is **ACTIVE/registered as
  a template set** (`site.template_sets` contains it) — run at `step_content_types`
  or `step_deploy`, NOT only via `component-validate` (too late). This single gate
  would have caught all 5 faults at the right step.
- [ ] **`check-cnd.mjs` additions** — detect: duplicate type across files; choicelist
  constraints-before-default; whitespace inside `subnodetypes=`/initializer CSVs;
  a self-referencing `<ns>mix:*` used in its own `subnodetypes`. Cheap, static, would
  have caught faults 2–5 pre-deploy.
- [ ] **Deterministic scaffold must include the full namespace header**
  (`jcr/nt/mix/j/jnt/jmix/<ns>/<ns>mix`) — the interactive `npm init` stalls the
  agent, so the fallback scaffold (hand/script-built) must not omit it (fault 1).
- [ ] **Wire site creation into the autonomous flow** — `site.create` (MCP) is an
  interactive `00-migration-start` step the loop's `step_connect` skips, so every
  pre-content render gate (`step_deploy /home`, content) 404s. `step_deploy` (or a
  new step) should `site.create` the siteKey with the module's template set if absent.
- [x] **Session reuse** — fresh `curl -u` per probe call blew the authenticated-visitor
  license cap (77/25). Probes that hit Jahia must reuse one session cookie (login once,
  reuse `JSESSIONID`), not auth per request. *(captured; helper TODO)*
