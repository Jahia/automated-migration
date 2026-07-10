# Review — lesalondelaphoto — round 1

## Gates

| probe | result | note |
|---|---|---|
| cnd-review | PASS | 15 CND files, score=1.00, no best-practice antipatterns |
| cnd-patterns | PASS | 16 CND files: mix:title, jmix:tagged/categorized, linkTypeInitializer, weakref images all compliant |
| no-stub | PASS | Every view emits real markup; every lsp: type has a registered view |
| components-all | PASS | 15 components: source paired, no stubs, en+fr i18n complete, builds clean |
| content.sh | PASS | All 47 pages have >400 chars live content |
| publish-parity.sh | PASS | 249 live content nodes, 0 broken weakrefs, 0 translation gaps |
| edit-frame.sh | PASS | Page Builder loads, 10 editable areas, footer blank (normal: AbsoluteArea-needs-children) |
| render-all.sh | PASS | All 47 pages render clean (no broken images, no collapsed regions, no opacity:0 content) |
| site-review.sh | **FAIL** | billetterie: critical (select-name) + serious (color-contrast) a11y; infos-pratiques/*: missing alt on img |
| fidelity-all.sh | **FAIL** | 47 pages without captured reference — capture-reference never ran, fidelity never verified |

## Findings

### 🔴 Critical

- **[critical] billetterie page** — `site-review.sh` reports 2 critical `select-name` violations on `<select>` elements (`.quantitySelect`) without accessible names. Affects screen-reader users. Location: rendered HTML on `/home/billetterie.html`. The ticketing embed (Secutix) injects these selects; aria-label or `<label>` association needed.

### 🟡 Major

- **[major] billetterie page** — 14 `color-contrast` violations (serious): elements `.step-ticketing`, `#resendLink` have insufficient contrast against background. WCAG 2.1 AA requires 4.5:1 for normal text, 3:1 for large text.

- **[major] infos-pratiques section (6 pages)** — `<img>` tags missing `alt` attribute:
  - `infos-pratiques.html` — 6 images without alt
  - `infos-pratiques/catalogue.html` — 1 image without alt
  - `infos-pratiques/comment-venir-au-salon.html` — 1 image without alt
  - `infos-pratiques/dates-acces-horaires.html` — 1 image without alt
  - `infos-pratiques/faq.html` — 1 image without alt
  - `infos-pratiques/photo-pass.html` — 1 image without alt
  These are likely background/decorative images rendered via components that don't expose an `alt` prop. Fix: add `alt` attribute to the view, sourced from a CND field or set to `""` for decorative images.

### 🔵 Minor

- **[minor] fidelity-all** — No `.reference/captured/` captures exist for ANY page. The `capture-reference` step was never executed. Without captured reference DOM, there is no automated fidelity verification that the migrated content matches the original site. Pages passed `render-truth` (no rendering defects) and `content.sh` (>400 chars), but semantic fidelity (are the right sections on the right pages with the right cards/facets?) is unverified.

## Verdict

**CHANGES REQUESTED**

Blocking issues:
1. `site-review.sh` fails on billetterie (critical a11y) and infos-pratiques (SEO: missing alt)
2. `fidelity-all.sh` fails because capture-reference was never run — no fidelity proof exists

The first issue (a11y/SEO) falls on the content step; the second (missing captures) is an upstream gap from the analysis phase. Both must be resolved before this migration can be approved.

---

*"Nothing ships without a reason."*
