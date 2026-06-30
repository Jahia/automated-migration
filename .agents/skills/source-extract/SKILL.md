---
name: source-extract
description: Deterministic, source-agnostic extraction of MEDIA and CONTENT from a captured website, plus DAM import and wiring. Use during analysis (extract) and before content creation (media import). Replaces LLM-improvised manifests — the captured DOM is the source of truth, the LLM only resolves ambiguous mapping.
---

# Source extraction — migration is ETL, not improvisation

## The principle (why this exists)

A migration is mostly a **deterministic ETL job**: parse the captured source DOM →
extract templates, components, **media**, **content** → emit CND + views + JCR nodes +
DAM assets. The LLM is only good at *judgment at the edges* (which component maps to
what, mixin design, ambiguous cases). When the LLM does the bulk extraction it does
the minimum to pass a gate and the result is hollow — the "0 of 40 images", "empty
listings", "placeholder text" failures.

So the bulk work is done by deterministic scripts, and they are **source-agnostic**:
every CMS (Sitecore SXA, Drupal, WordPress, AEM, plain HTML) serves rendered HTML, so
the captured DOM is the universal source of truth.

```
capture (any HTML)  ──►  detect CMS  ──►  extract media (generic)  ──►  import to DAM  ──►  wire
                                     └──►  extract content (adapter + generic)  ──►  load to JCR
                                                                                       │
                                                                  verify live vs the real source
```

## The deterministic scripts (orchestration/lib + images)

| Script | Input | Output | Agnostic? |
|---|---|---|---|
| `lib/source_detect.py <project>` | captured DOM | `<project>.source.json` (sitecore-sxa / drupal / wordpress / aem / generic) | yes |
| `lib/extract_media.py <project> <site>` | captured DOM | `images/<project>.json` (per-page image manifest: src, file, role) | **fully generic** — parses `<img>`/srcset/`<source>`/`url()`/og:image |
| `lib/extract_content.py <project> <site>` | captured DOM | `content/<project>.content-data.json` (per-page real field values / blocks) | generic + adapter (SXA `field-*` precise) |
| `images/import.py <project>` | `images/<project>.json` | `images/<project>.imported.json` (page → DAM jcrPath) | yes (jahia-image-proxy servlet) |
| `images/set_image_refs.py` / `set_hero_refs.py` | imported.json | image weakrefs set on content | yes |

## Where it sits in the workflow (the plan)

- **epic_foundation → `step_extract`** (after analyze): run source_detect + extract_media +
  extract_content. Gate `extract.sh` — manifests must be complete and cover home.
- **epic_content_quality → `step_media`** (after deploy, before content): run `import.py`
  to push every manifest image into the DAM. Gate `media.sh` — import must cover the manifest.
- **epic_content_quality → `step_content`**: **LOAD** `content-data.json` into the JCR and
  wire the imported media; do NOT improvise. Gate `content.sh` (now reality-grounded:
  content-fidelity + fidelity-all, no char-count proxy).
- **epic_fidelity_golive → `step_visual_diff`**: `fidelity-all.sh` renders live vs the real
  cached source and compares.

## Gates (no proxies — grounded in the real source)

- `extract.sh` — extraction is complete (media covers pages incl. home; content has real text, not placeholders).
- `media.sh` — every manifest image landed in the DAM.
- `content.sh` — **content-fidelity** (live JCR has images set / listings exist / shell populated / EN / no debris) **+ fidelity-all** (render live vs the real cached source, compare sections/cards/images). No `>N chars` proxy — that passes filler.
- `content-fidelity.sh` / `fidelity-all.sh` — see those probes.

## Adding a new CMS adapter

The generic path always works. To improve precision for a CMS:
1. Add its signatures to `SIGNATURES` in `source_detect.py`.
2. In `extract_content.py`, add an adapter class (like `SXAContent`) that knows the CMS's
   component/field markup (Drupal `field--name`, WP `entry-content`/blocks, AEM `cq`/`data-sly`),
   and select it in `main()` by the detected source. `extract_media.py` rarely needs changes
   (image markup is universal).
3. Never hard-fail on an unknown CMS — fall through to `GenericContent`.

## Hard rules

- **Never hand-author or LLM-improvise the media/content manifests.** They come from the
  captured DOM via the scripts. The LLM may correct an ambiguous mapping, not invent content.
- **Never re-fetch from the origin when a capture exists** (WAF). Import via the proxy or
  from cached/MHTML bytes.
- **Verify against the real source**, never a threshold. If unsure, screenshot live vs the
  captured original and look.
