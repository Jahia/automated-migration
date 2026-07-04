# orchestration/probes — migration quality gates

Each probe is a small, READ-ONLY (unless noted) checker that a migration must pass.
Gates exit non-zero to BLOCK; report-mode probes always exit 0. Full pipeline
wiring is in `orchestration/ANALYZE-PIPELINE.md §3`; contribution rules in
`.claude/rules/migration.md §22-33`.

## The composability gate — `composability.py` (P6, Pillar 4)

Measures editable **structure** (the half G1/G6 miss). G1 scores editable text, G6
scores whether wired fields are reachable — neither catches "one big component for
the whole page with as many properties as needed" (Julian, 2026-07-04). That model
is pixel-perfect and text-editable yet NOT composable (the contributor cannot add /
reorder / remove blocks). `composability.py` quantifies exactly that debt.

READ-ONLY. Reads three on-disk artifacts (no Jahia, no network):
`projects/<p>/settings/definitions.cnd`, `.../workflow-output/component-manifest.json`,
`orchestration/content/<p>.content-load.json`.

### Gate contract (calibrated P6.1 — K=8 LOCKED by Julian, 2026-07-04)

| Mode | Behaviour |
|---|---|
| default (`--report`) | prints all metrics, **always exit 0** |
| `--gate` | exit **non-zero** iff **(a)** any type has an instance with **> K lifted editor fields** (K=8) **OR** **(b)** any **full-page monolith** exists (frozen skeleton `>= --mono-bytes`, default 8000). |

- **Lifted fields** on an instance = `|fields − {html, skeleton}| + |media| + (1 if link)`.
- The **composable ratio** (typed atoms / all nodes) is **REPORTED but NOT gated**.
  It becomes a blocking floor only after P6.2 decomposition runs (plan Pillar 4). So
  today the hard gate enforces *no page-in-one-component and no full-page monolith*,
  without yet demanding a composability minimum.
- A **frozen type** = a type whose CND declares `skeleton`/`html` OR a **numbered body
  run** (`body2+`). A lone `body` richtext field is a LEGIT atom field (e.g. the base
  library's `$NS:richText` / `$NS:card`) and does NOT mark a type frozen.

### Why K=8 is safe (calibration evidence, P6.1)

Verified against acquia + supercar's richest types: **every** type over K=8 in the 4
baselines is the debt the gate targets — a skeleton/body-run aggregate
(acquia `content-listing` K=27 = 18 body*; supercar `content` K=34 = 18 body*;
the borderline acquia card `ct-article--card-wrapper` K=9 exceeds 8 ONLY because it
carries `body`+`body2`+`body3`+`body4`, the un-decomposed numbered-run anti-pattern).
**No legitimate library-shaped component exceeds 8**: the richest base-library atom,
`$NS:card`, has 6 node-level fields (title, body, image, imageAltText, theme,
cornerCut); its `tag`/`button` are CHILD nodes, not lifted fields. A rich article
card decomposed to heading + richText + N images + cta stays well under K.
Any future legit case that trips K must be **escalated to Julian**, never raised
unilaterally (locked decision, MODULARITY-PLAN §5b).

### Usage

```
composability.py <project> [--k 8] [--mono-bytes 8000] [--gate] [--json]
```

### Baselines (4 reference projects, calibrated P6.1 — pre-P6.2, so all FAIL the gate)

These are the DEBT the P6.2 decomposition must clear; they are expected to fail the
hard gate today (the gate guards future P6.2-generated models against regression).

| project | composable ratio (reported) | types over K=8 | monoliths | gate |
|---|---|---|---|---|
| acquia-drupal   | 57.0% | 8  | 3  | FAIL |
| supercar-garage | 53.4% | 4  | 1  | FAIL |
| contentful      | 31.2% | 7  | 7  | FAIL |
| discoverasr     | 0.0%  | 13 | 53 | FAIL |

## The base component library (the composability VOCABULARY, P6.1)

The palette these metrics push migrations toward lives in
`orchestration/templates/base-library/` (project-agnostic, `$NS`/`$NSMIX` stamped by
`orchestration/lib/install_base_library.py`). It is generalized from the DEPLOYED
`lesalondelaphoto` module (typed atoms → composable containers → per-page-type zones)
and COEXISTS with the `fidelity-shell` `$NS:rawHtml` passthrough (the byte-exact
safety net — fidelity-first). See `orchestration/LIBRARY-SPEC.md`.
