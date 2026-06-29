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
- [ ] **publish-parity.sh** — every weakreference (images, linknodes) and every
  i18n property on published content resolves in **LIVE** for each language.
  Catches: unpublished DAM, the `languages:[fr]` gap, stubborn 404 files.
- [ ] **edit-frame.sh `<page>`** — load `/cms/editframe/...`; each shared region
  (header/nav/footer) and each listing renders non-empty AND shows editable
  markers. Catches: AbsoluteArea-needs-children, blank footer in Page Builder.
- [ ] **fidelity-live.sh** — diff against the **live** reference via browser
  (not cache): section order, card/item counts, facet values. Replaces the weak
  `fidelity.sh` (headings-only — passed visually-wrong pages).
- [ ] **no-stub.sh** — every CND type has a non-trivial view (LOC/AST threshold,
  not just a present file), a resource-bundle label+tooltip, and an icon; every
  registered component renders without throwing.
- [ ] **theme-coupling.sh** — scan imported CSS for `:not(.x){opacity:0}` reveal
  patterns (assert a reveal observer exists) and orphan SXA `facet`/`search`
  markup with no backing listing.

## Skills

- [ ] **New `capture-reference` (browser-first)** — for JS/WAF sites, Chrome MCP
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
- [ ] Decompose heavy steps (asset import, view implementation, content) into
  per-artifact units with per-artifact gates, so a stubbed 29/32 fails at once.
- [ ] Per-page sign-off gate: render-truth + fidelity-live + publish-parity,
  producing a screenshot-vs-reference artifact.
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
2. browser-first `capture-reference` skill ← **next**
3. `publish-parity.sh` + the `languages:[…]` publish rule
4. `edit-frame.sh`
5. `fidelity-live.sh` replacing `fidelity.sh`
6. decompose loop steps + `no-stub` gate
