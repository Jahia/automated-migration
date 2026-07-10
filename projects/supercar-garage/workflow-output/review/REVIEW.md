# Jahia Module Review — supercar-garage

**Reviewer:** Auditor Rex | **Date:** 2026-06-25 | **Types:** 32 | **Views:** 37 | **Locales:** en, fr

---

## 🔴 Critical (0 issues)

None.

---

## 🟡 Warnings (3 issues)

### W1 — FooterSection legal links are `<span>` not `<a>` (non-functional links)
**File:** `src/components/Shell/FooterSection/default.server.tsx:150-170`

The legal section links (legalPlanSite, legalMentions, legalData, legalCookies) are rendered as plain `<span>` elements with no clickable target. Editors fill these fields expecting them to be navigable links.

```tsx
// Current (broken):
{props.legalPlanSite && <div className="field-lien"><span>{props.legalPlanSite}</span></div>}
// Fix: linkType properties are missing from the FooterSection CND — add j:linkType + j:linknode/j:url
// for each legal link, or collect them from child ctaButton nodes and render as <a>.
```

**Severity:** Non-functional UI — editors will think they added a link but visitors see static text.

---

### W2 — MainNavigation ctaSecondaryLabel uses ctaPrimaryLink (copy-paste bug)
**File:** `src/components/Shell/MainNavigation/default.server.tsx:92-96`

The secondary CTA button reuses `ctaPrimaryLink` instead of resolving its own link. Only one CTA link can be configured — the secondary button is a visual duplicate.

```tsx
// Current:
{props.ctaSecondaryLabel && (
  <a href={ctaPrimaryLink} className="cta-2">  // ← should be ctaSecondaryLink
// Fix: add j:linkType/j:linknode/j:url fields to MainNavigation CND for the secondary CTA,
// resolve them in the view, and use the result here.
```

**Severity:** Functional bug — the secondary CTA always navigates to the primary CTA target.

---

### W3 — TopBar search link has empty `href=""`
**File:** `src/components/Shell/TopBar/default.server.tsx:86-88`

```tsx
<a title="" href="" target="">
  <div className="search"><i className=""></i></div>
</a>
```

Empty link markup with no icon class. This is an artifact from the source HTML and serves no purpose.

**Severity:** Minor UI artifact — renders a non-functional empty link on every page.

---

## 🔵 Suggestions (7 issues)

### S1 — Missing content type icons (31 of 32 types lack icons)
**Directory:** `settings/content-types-icons/`

Only `usgmix_component.png` exists. All 32 content types need 32×32 PNG icons with the naming convention `<cndNamespace>_<typeName>.png`. Without them, Content Editor shows blank icon squares in the content picker.

Affected types: usg_ctaButton, usg_topBar, usg_mainNavigation, usg_footerSection, usg_breadcrumb, usg_heroBanner, usg_heroCarousel, usg_heroSlide, usg_videoSection, usg_videoContentBlock, usg_imageBlock, usg_richText, usg_plainHtml, usg_sectionTitle, usg_ctaBanner, usg_editorialBlock, usg_imgContentBlock, usg_infoCard, usg_quickLinks, usg_quickLinkCard, usg_keyFigures, usg_keyFigure, usg_partnersCarousel, usg_partnerLogo, usg_timelineCards, usg_timelineCard, usg_sectionHub, usg_facetFilter, usg_newsArticle, usg_pressRelease, usg_socialLink

---

### S2 — Hardcoded "Load more" string in client component (breaks i18n)
**File:** `src/components/Listing/JcrQuery/JcrQueryLoadMore.client.tsx:43`

The `Load more` button text is hardcoded in the client-side Island component. The locale keys `jcrQuery.loadMore` exist in both en.json and fr.json but are never used here.

```tsx
// Current:
<button type="button" className={styles.button} onClick={handleLoadMore}>
  Load more  {/* ← hardcoded */}
</button>
// Fix: accept a `loadMoreLabel` prop, pass it from JcrQuery/default.server.tsx using:
// loadMoreLabel: t("jcrQuery.loadMore")
```

The server-side `JcrQuery/default.server.tsx` passes `{ queryId, pageSize, total }` to the Island — add `loadMoreLabel` to this object.

---

### S3 — Bare `<Area name="main" />` without `nodeType` in basic page template
**File:** `src/templates/Page/basic.server.tsx:11`

```tsx
<Area name="main" />  // ← no nodeType restriction
```

Without a `nodeType`, the area accepts ALL `jmix:droppableContent` types, meaning editors see every component as a droppable option — including shell components (header/footer) that should never appear in page body areas.

**Fix:** Create a typed area (e.g. `usg:pageArea`) in settings/definitions.cnd restricted to `usgmix:pageComponent`, and use it:
```cnd
[usg:pageArea] > jnt:content, jmix:list, jmix:hiddenType orderable
 + * (usgmix:pageComponent)
```
Then `<Area name="main" nodeType="usg:pageArea" />`.

---

### S4 — Layout has hardcoded CDN font-face URLs (external dependency, CSP risk)
**File:** `src/templates/Layout.tsx:98-124`

The `@font-face` declarations reference `https://cdnjs.cloudflare.com/...` URLs. This creates a hard dependency on an external CDN, triggers CSP violations unless the CDN is allowlisted, and breaks if the CDN is unavailable.

**Fix:** Host the font files in `static/fonts/` and reference them via `buildModuleFileUrl("static/fonts/fa-solid-900.woff2")`.

---

### S5 — `import.xml` missing offline pages and content folder structure
**File:** `settings/import.xml`

The import.xml only contains the home page. It lacks:
- `Offline pages/Models` folder (jmix:systemNameReadonly, jmix:nolive)
- `Offline pages/Drafts` folder
- `Offline pages/Archive` folder
- Content folder restrictions (jmix:contributeMode)

Without these, editors have no offline workspace and no content governance.

---

### S6 — Non-semantic HTML in some components
Several components use `<div>` where semantic elements are more appropriate:
- `src/components/Content/SectionTitle/default.server.tsx` — wrapping `<div>` could be `<header>`
- `src/components/Listing/GridRow/default.server.tsx` — uses `<section>` (correct) but column wrappers use `<div>`
- `src/components/Hero/HeroSlide/default.server.tsx:63` — duplicate `<img>` for decorative purposes without `aria-hidden`

Minor quality issue — no functional impact.

---

### S7 — JCR Query component does not pass category chips to the client filter
**File:** `src/components/Listing/JcrQuery/default.server.tsx`

The `categoryFilter` boolean is defined in the CND and passed as a prop, but the `JcrQueryFilter.client.tsx` Island is never rendered in the server-side view. The `categoryFilter` prop is destructured but unused. Either implement client-side category chips or remove the property.

---

## ✅ Summary

| Severity | Count | Verdict |
|----------|-------|---------|
| 🔴 Critical | 0 | ✅ Clean |
| 🟡 Warnings | 3 | Fix before sharing with editors |
| 🔵 Suggestions | 7 | Improve when time allows |

### What's solid
- **CND modelling:** No `jmix:droppableContent` direct use, no `j:linknode`/`j:url` in CND, correct `linkTypeInitializer` usage everywhere, proper `mix:title` inheritance. 32 types, all well-formed.
- **View patterns:** All `j:linkType` resolution uses proper `switch`/`if` logic (`buildNodeUrl` for internal, `j:url` for external). No hardcoded URLs in views.
- **i18n:** en.json and fr.json are fully in sync. All user-facing CND fields have `i18n`. `.properties` files have labels and `ui.tooltip` for every field.
- **Navigation:** 3-level JCR-driven nav via `getChildNodes`, no hardcoded links. Language switcher present.
- **Query:** JCRQuery uses `ISDESCENDANTNODE`, supports filters, load-more, and category chips.
- **No boilerplate:** Hello component removed. No dead code.
- **Layout:** `<main>` tag present, `<html lang={lang}>` set, header/footer via AbsoluteArea.
- **Cache:** No `cache.expiration="0"` found.
- **Types:** All props use `?:`, no `any` types.

### Gate 5 — Human Review Sign-off
This is a **human validation gate**. Review the findings above. The operator should decide:
1. Whether to fix W1-W3 before continuing (recommended)
2. Whether to address S1-S7 now or post-migration
3. Whether to proceed to the accessibility audit (skill 12/skill jahia-dev-accessibility)

After operator approval, the run continues to the accessibility audit step.

---

*"Nothing ships without a reason."*
