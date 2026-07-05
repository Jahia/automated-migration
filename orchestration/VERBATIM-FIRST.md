# Verbatim-first page assembly & the 0-DOM-change gate

Target (Julian, 2026-07-05): **the migrated page's rendered DOM is structurally
identical to the source's visible DOM — zero differing content nodes.** Stronger
and more honest than the pixel gate: it catches invisible changes (a dropped
`hidden` element, a reordered wrapper) that pixels miss. It would have caught the
"drop hidden elements" regression.

## Definition of the gate (`dom_diff`)

Compare the **visible DOM**, structurally (Julian's ruling "DOM visible, structurel"):
- **Strip runtime-only nodes from BOTH sides**: `script / noscript / template / style
  / meta / link / base / head / title` + comments. Jahia emits no Next.js/hydration
  runtime, so those are not comparable and carry no visible structure.
- **Ignore volatile/hydration attributes** (React/Next/Turbo/Svelte hydration ids,
  ephemeral streaming ids `B:0`/`S:1`, react keys) — non-semantic, framework-injected.
- Compare `tag + attributes + own-text + document order`. Metric = number of
  differing content nodes. **Target = 0.**
- **Jahia injects NO wrappers into the DOM (Julian).** The render == exactly what our
  views emit, so there is nothing framework-specific to normalise on our side; any
  diff is 100% our assembly and therefore fixable.

Two run modes:
- **reconstruct (model stage / S3 proxy)**: rebuild the page from the content-load
  the SAME way `Layout.tsx` does (shell fold + chrome + zones), diff vs the frozen
  mirror. Fast, pre-deploy, approximate (must mirror the render exactly).
- **render (ground-truth / true gate)**: fetch the deployed EDIT render, diff vs the
  frozen mirror. Authoritative. This is where 0 is enforced.

Probe: `orchestration/probes/dom_diff.py`.

## The architecture is already verbatim-oriented

`page_shell(html)` (extract_content.py) already captures, verbatim:
- `bodyAttrs`, `mainAttrs`;
- `levels` — the `<body>`→`<main>` ancestor chain, each with `before`/`after`
  sibling markup preserved byte-exact;
- `innerLevels` — the `<main>`→content-root chain (e.g. Drupal `region--content`,
  Next.js `__className_*` wrapper), same `before`/`after`;
- `head`.

`Layout.tsx` folds them back: `<body bodyAttrs>` + chrome AbsoluteAreas +
`levels` reduceRight (wrappers with `before`/`after` `Raw`) + `<main mainAttrs>` +
`innerLevels` reduceRight + the content Areas (`z1..zK`, `main`). Content nodes
render their skeleton with `{{f:*}}`/`{{media:*}}`/`{{link:href}}`/`{{child:N}}`
substituted — an unedited node is byte-identical to source (rule 22).

So "verbatim-first at page level" = **make this fold reproduce the source body
byte-exact**, and enforce it with `dom_diff`. Extends rule 22 (section) to the page.

## Invariants (must hold for 0-DOM)

1. **Nothing removed.** Non-rendered/invisible markup (`hidden`, body `<style>`/
   `<link>`, streaming markers) is kept verbatim (flagged `nonRendered`), never a
   zone, never painted — but present so the render is byte-exact (fixed 2026-07-05).
2. **Nothing repositioned.** Chrome/scaffold/wrappers render at their SOURCE
   position. A site-wide singleton scaffold (grid overlay) is template-level but
   must land where it was, not in a floating area.
3. **No double render.** Chrome that lives in `levels.before/after` verbatim must
   NOT also render as an AbsoluteArea (and vice-versa) — exactly one source of truth.
4. **Order preserved.** Zones and their instances render in document order.
5. **Byte-exact per node** (existing `wrapper_container`/skeleton self-check;
   fallback to verbatim rawHtml when recompose ≠ source).

## Known drift sources to close (hypotheses to confirm with dom_diff)

- content-root wrapper altitude (`__className_*`): captured in `innerLevels`? must
  wrap the Areas, not be dropped.
- chrome double-render vs `chromeAreas` flag (invariant 3).
- zone arrangement: wrapper markup BETWEEN sibling zones must be captured
  (`before`/`after` between top-level bands), else zones concatenate wrong.
- nonRendered instances rendering at the right position.

## Acceptance

`dom_diff` (render mode, deployed EDIT vs mirror) reports **0 differing content
nodes** on every page, on all 5 reference stacks (Drupal / Next.js / AEM-SPA /
Liferay / SXA). Reported per page; any residue is enumerated (no silent tolerance).
