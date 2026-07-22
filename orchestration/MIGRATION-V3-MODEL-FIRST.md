# Migration v3 — MODEL-FIRST, from scratch on any distant site

Operator mandate (2026-07-21): "a generic approach for any website out there
— rediscovering a distant site from scratch." This document IS the doctrine;
gen_plan emits it. Site-specific inputs are exactly THREE: the start URL,
the approved component model, and the entity config the model emits.
Everything else is identical machinery.

The division of labor that days of singpost grinding proved:
- **Determinism executes** — crawling, extraction, loading, publishing,
  measuring. Reproducible, resumable, gated. Never judgment.
- **The model judges ONCE, reviewably** — Claude reads the corpus and
  authors the component model; the operator amends and approves it; the
  machinery compiles and EXECUTES it. Judgment never hides inside
  thresholds again.

## Phase 0 — CAPTURE (deterministic, source-agnostic)

1. `source_detect` fingerprints the stack (Astro/Next/AEM/Drupal/SXA…) and
   picks extraction adapters.
2. **The menu is the IA truth**: extract the real navigation (nav DOM or
   hydration props), derive the sitemap from it — sections, synthetic
   groups, labels. Crawl every menu-linked URL (nav-scoped, not BFS-random:
   the 18-random-pages failure), plus assets. WAF backoff, cache-to-disk,
   post-hydration DOM.
3. Localize into a self-contained mirror (`local-mirror/<slug>.html`) — the
   byte source of truth for everything downstream.
4. Ledgers: page inventory, asset inventory, LINK CENSUS (internal /
   external / uncrawled-by-prefix — the uncrawled clusters are the entity
   candidates and the scope questions).

## Phase 1 — UNDERSTAND (Claude judgment, bounded and reviewable)

5. `model_census` (deterministic): section families across the corpus
   (anatomy signatures: grid/carousel/collapsible/table/aside), repeated
   patterns, entity-shaped clusters (dated prose reached from cards, never
   from the menu), CTA anatomies, chrome regions.
6. **Claude authors the component model** from the census + representative
   DOMs + screenshots: `component-model.md` (human) + `component-model.json`
   (machine). Contents:
   - **atoms**: cta (variant: primaryButton/secondaryButton/textArrow/
     iconLink), teaserCard (title/teaser/image/date + cta)
   - **composites**: the bounded set (hero, cardGrid, promoBand,
     richTextSection, accordion, contentList, subNavigation) — each with
     FIELDS and VIEW FAMILIES (one component, many views; never one type
     per page-occurrence)
   - **entity map**: jmix:mainResource folders (type, urlPrefixes,
     listingPages) under the derived rule — nav-reachable = page;
     card-reached prose = entity; ties break to page (menus never hole)
   - **chrome**: siteHeader/mainNavigation(+ section switcher)/footer
   - **css slots**: named classMap slots per type (captured source classes)
     over the semantic fallback skin
   - **islands**: which captured behaviors get adopted (SourceCarousel
     pattern: server markup byte-identical, behavior attaches)
   - **scope report**: uncrawled clusters with a recommendation each
7. **OPERATOR REVIEW GATE** (engine decision point — the run pauses): amend
   names, fields, views, entity map, scope. The approved model is the
   contract for everything after.

## Phase 2 — COMPILE (deterministic, FROM the model)

8. `apply_component_model` patches the manifest (names, view families,
   additive fields); `cnd_emit`+`merge_cnd` emit CND + types + EN/FR bundles
   with tooltips; `install_shell_templates` emits views (hybrid default +
   semantic variants + query views + tree-driven nav/subnav + mainResource
   content templates + islands); the model's entity map lands as
   `<p>.mainresource.json`. Nothing is hand-patched; re-running is
   idempotent. nodeType identifiers are FROZEN at first deploy (renaming
   deployed types bricks the JCR registry) — the model governs names,
   fields, views.

## Phase 3 — LOAD (deterministic executors, EDIT-only)

9. Pages from the IA (create_pages + build_nav_tree: sections, moves,
   source menu ORDER per section, labels; entity slugs excluded).
10. Entities from the mirror DOM (`load_main_resources`: contentFolder +
    node per detail — title/date/hero-weakref/body; never dependent on
    segmentation).
11. Content into the model's fields (`extract` + `semanticize`): every
    class we burned is a built-in pass — images out of richtext into
    weakref units (galleries → children; table-nested stay as DAM richtext
    refs), sub-navs → tree-driven, entity listings → real queries,
    decomposition-residue dedup, marker-into-root, slot normalization.
12. At WRITE time (one choke point): internal hrefs → Jahia page URLs,
    entity hrefs → node renders (fragments preserved), raster assets → DAM.
    Chrome populated as editable content, links refreshed on every run.
13. Publication is the SINGLE FINAL ACT (files → contents → chrome → pages,
    unpublish-first, adaptive poll).

## Phase 4 — PROVE (the gate wall; a red names its producer)

Artifact gates: reconcile (word conservation / leftover ceiling / frozen
raster in richtext / menu-as-content / frozen entity listing / node-type
ledger / cta shells / slot pairing). Render gates: clean-render, dam-ref,
link-integrity, cta-link, chrome-render, startnode+mainresource,
model-contract. Truth gates: publish integrity belt, groundtruth pixel
(masked, EDIT preview, JS-off both sides), scorecard (pixel/junk/IA/
completeness — BLOCKING). Functional gates: interactions actually work
(carousel arrows move the track — probe clicks, not assumptions).

## What stays site-specific — and nothing else

| Input | Producer |
|---|---|
| Start URL + locale set | operator |
| Approved component model | Claude authors, operator amends (Phase 1) |
| Entity/scope decisions | the model's scope report + operator |

Everything else — every extractor, every rewire, every gate, every view
template — is the same code for every site. A new source flavor adds an
ADAPTER (detection + extraction), never a fork of the pipeline.
