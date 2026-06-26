---
name: 5-implement-navigation
description: Implement the MainNavigation component with 3-level JCR-driven navigation. Mandatory for every migration. Never hardcode nav links.
type: production
phase: 5
status: active
depends_on:
  - 4-define-content-types
allowed-tools: Bash, Read, Write, Edit
---

# Skill: Implement Navigation

Builds the canonical Jahia navigation component: JCR-driven, 3 levels deep, language-aware. **Never hardcode nav links.**

See also: `.agents/context/jahia-navigation-patterns.md` for the full helper function reference.

---

## Agent identity
- **Agent name:** Navitar
- **Reference style:** Cartography / wayfinding
- **Signature line (en):** *"Three levels. One tree. No hardcoded links."*
- **Personality note:** Rigorous about the 3-level rule and the 4 nav item types. Will not let a nav skip level 3 just because it's inconvenient.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## FIRST: Inspect the source site header structure

> CSS grid patterns reference: `.agents/context/jahia-css-framework-conflicts.md` — "CSS Grid header layouts" section.


Before writing any code, check whether the source site positions the navigation using CSS grid:

```bash
grep -n "grid-area\|grid-template\|display.*grid" static/css/*.css | grep -i "nav\|header" | head -20
```

**Two architectural patterns emerge — choose the right one:**

### Pattern A: Standalone nav (no grid dependency)
The navigation element is positioned independently (flexbox, float, or block flow). The `ns:mainNavigation` view can output just the `<nav>` element.

### Pattern B: Nav is a CSS grid child (full-header pattern)
The CSS positions `navigation-main` (or equivalent) as a `grid-area` inside a parent grid. This means the nav **cannot exist without its grid parent**.

**In Pattern B, the `ns:mainNavigation` view MUST output the complete `<header>` structure** — including the grid container, the logo, the dates/headline, the ticket CTA, and the nav. All of these are grid items. If you only output `<div class="navigation-main">`, the browser has no grid parent and the layout collapses or spreads to full viewport width.

To confirm Pattern B:
```bash
# Does navigation-main have a grid-area assignment?
grep -n "navigation-main" static/css/*.css
# Does its parent .grid have display:grid?
grep -n "\.grid\b" static/css/*.css | head -10
```

If Pattern B: the view also needs to render the logo, the top bar (social icons, CTAs), and any other header elements. Pull those from the analysis — they were likely identified as separate components but must be co-located in the header view since they share a grid parent.

---

## CND definition

`MainNavigation` has no editable properties by default — all nav data comes from the JCR page tree at render time. However, if the header includes configurable elements (logo image, CTA label, ticket button link), add those as fields:

```cnd
// src/components/Navigation/MainNavigation/definition.cnd
[ns:mainNavigation] > jnt:content, nsMix:pageComponent
  // Add fields only for content editors need to configure:
  // - logoImage (weakreference, picker[type='image'])
  // - exposantCtaLabel (string) i18n
  // - j:linkType (string, choicelist[linkTypeInitializer])
```

For a pure nav with no configurable header elements:
```cnd
[ns:mainNavigation] > jnt:content, nsMix:pageComponent
```

---

## Helper functions

```tsx
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { getChildNodes, buildNodeUrl } from "@jahia/javascript-modules-library";

/** Nav-eligible children: must be navMenuItem, must not be a navMenu container */
const getNavItems = (node: JCRNodeWrapper): JCRNodeWrapper[] =>
  getChildNodes(node, -1, 0, (n) => {
    if (!n.isNodeType("jmix:navMenuItem")) return false;
    if (n.isNodeType("jmix:navMenu")) return false;
    return true;
  });

/** Resolve href for jnt:page, jnt:nodeLink, jnt:externalLink */
const getItemUrl = (node: JCRNodeWrapper): string => {
  try {
    if (node.isNodeType("jnt:page")) return buildNodeUrl(node);
    if (node.isNodeType("jnt:nodeLink") && node.hasProperty("j:node"))
      return buildNodeUrl(node.getProperty("j:node").getNode() as JCRNodeWrapper);
    if (node.isNodeType("jnt:externalLink") && node.hasProperty("j:url"))
      return node.getProperty("j:url").getString();
  } catch (_) {}
  return "#";
};

/** Display title — resolves across all 4 nav item types */
const getItemTitle = (node: JCRNodeWrapper): string => {
  try {
    if (node.isNodeType("jnt:nodeLink") && node.hasProperty("j:node")) {
      const ref = node.getProperty("j:node").getNode() as JCRNodeWrapper;
      if (ref.hasProperty("jcr:title")) return ref.getProperty("jcr:title").getString();
      return ref.getName();
    }
    if (node.hasProperty("jcr:title")) return node.getProperty("jcr:title").getString();
  } catch (_) {}
  return node.getName();
};
```

---

## 3-level render pattern

```tsx
import {
  buildNodeUrl, getChildNodes, getSiteLocales,
  jahiaComponent, useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import styles from "./mainNavigation.module.css";

jahiaComponent(
  { componentType: "view", nodeType: "ns:mainNavigation", displayName: "Navigation principale" },
  () => {
    const { renderContext, currentResource } = useServerContext();
    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;
    const level1Items = getNavItems(homePage);

    const currentLang = currentResource.getLocale().getLanguage();
    const siteLocales = getSiteLocales();
    const showLangSwitcher = Object.keys(siteLocales).length > 1;

    return (
      <>
        <nav id="main-nav" role="navigation" aria-label="Main navigation"
             className={styles.nav} data-expanded="false">
          <div className={styles.inner}>
            <ul className={styles.navItems}>
              {level1Items.map((item) => {
                const isMenuText = item.isNodeType("jnt:navMenuText");
                const level2Items = getNavItems(item);
                const hasL2 = level2Items.length > 0;

                return (
                  <li key={item.getPath()} className={hasL2 ? styles.hasDropdown : styles.navItem}>
                    {isMenuText ? (
                      <span className={styles.navLabel}>{getItemTitle(item)}</span>
                    ) : (
                      <a href={getItemUrl(item)} className={styles.navLink}
                         data-nav-path={item.getPath()}>
                        {getItemTitle(item)}
                      </a>
                    )}

                    {hasL2 && (
                      <ul className={styles.dropdown}>
                        {level2Items.map((sub) => {
                          const level3Items = getNavItems(sub);
                          const hasL3 = level3Items.length > 0;
                          return (
                            <li key={sub.getPath()} className={hasL3 ? styles.hasFlyout : ""}>
                              <a href={getItemUrl(sub)} className={styles.dropdownLink}>
                                {getItemTitle(sub)}
                              </a>
                              {hasL3 && (
                                <ul className={styles.flyout}>
                                  {level3Items.map((deep) => (
                                    <li key={deep.getPath()}>
                                      <a href={getItemUrl(deep)} className={styles.flyoutLink}>
                                        {getItemTitle(deep)}
                                      </a>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>

            {showLangSwitcher && (
              <ul aria-label="Language selection" className={styles.langSwitcher}>
                {Object.keys(siteLocales).map((langCode) => {
                  const isCurrent = langCode === currentLang;
                  const url = buildNodeUrl(
                    renderContext.getMainResource().getNode() as JCRNodeWrapper,
                    { language: langCode }
                  );
                  return (
                    <li key={langCode}>
                      <a href={url} lang={langCode}
                         aria-current={isCurrent ? "true" : "false"}
                         className={isCurrent ? `${styles.langLink} ${styles.active}` : styles.langLink}>
                        {langCode.toUpperCase()}
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </nav>

        {/* Mobile toggle + active link script — no React island needed */}
        <script dangerouslySetInnerHTML={{ __html: `(function(){
  var toggle = document.querySelector('[data-mobile-nav-toggle]');
  var nav = document.getElementById('main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function() {
      var exp = nav.getAttribute('data-expanded') === 'true';
      nav.setAttribute('data-expanded', String(!exp));
      toggle.setAttribute('aria-expanded', String(!exp));
    });
    document.addEventListener('click', function(e) {
      if (nav.getAttribute('data-expanded') === 'true'
          && !nav.contains(e.target) && !toggle.contains(e.target)) {
        nav.setAttribute('data-expanded', 'false');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }
  var raw = window.location.pathname;
  var jcrPath = raw.replace(/^\\/(?:fr|en|es)(\\/|$)/, '$1').replace(/\\.html$/, '').replace(/\\/$/, '') || '/';
  document.querySelectorAll('[data-nav-path]').forEach(function(link) {
    var navPath = link.getAttribute('data-nav-path');
    if (jcrPath === navPath || jcrPath.startsWith(navPath + '/'))
      link.setAttribute('aria-current', 'page');
  });
})();` }} />
      </>
    );
  }
);
```

---

## Resource bundle entries (mandatory + ui.tooltip)

```properties
ns_mainNavigation=Navigation principale
ns_mainNavigation.ui.tooltip=JCR-driven navigation menu. Reads from the site page tree automatically.
```

---

## SiteHeader (hamburger trigger)

SiteHeader and MainNavigation are **two separate components** — both dropped in the same `header` absolute area. They communicate via `data-mobile-nav-toggle` attribute (no React context, no Island needed).

SiteHeader must include:
```tsx
<button data-mobile-nav-toggle aria-expanded="false" aria-controls="main-nav"
        aria-label={t("header.mobileNav.toggle")}>
  {/* hamburger icon */}
</button>
```

---

## Gotcha: imported theme makes the nav an off-canvas panel (verified on sial-paris)

When you import a site's compiled theme CSS, the desktop horizontal menu and the mobile menu are usually **two different layouts gated by `@media`**, and the mobile one is an off-canvas panel hidden until a class is toggled. On sial-paris the theme did:

```css
@media (max-width: 1199.98px) { .navigation-main { position: fixed; left: -1400px; } }   /* off-screen */
.navigation-main.is-open { transform: translateX(1400px); }                               /* slid in */
@media (min-width: 1200px)   { .level1:hover .clearfix { display: block; position: absolute; } }  /* desktop dropdown */
@media (max-width: 1199.98px){ .level1.submenu-open .clearfix { display: block; } }        /* mobile accordion */
```

Consequences you MUST handle, or the menu is dead below the desktop breakpoint:
- **The toggle button must actually be RENDERED.** A `querySelector('[data-mobile-nav-toggle]')` that finds nothing = the off-canvas never opens; the whole menu is invisible on every laptop/tablet/phone under the breakpoint. Render the `<button data-mobile-nav-toggle>` in the markup, not just reference it in JS.
- **Toggle the class the THEME expects** (here `.is-open` on `.navigation-main`), not an invented one like `data-expanded`. Read the theme CSS to find the real open mechanism.
- **Wire the submenu accordion for mobile** by toggling the theme's class (here `submenu-open`) on click of `.level1.submenu > .navigation-title`, guarded by `matchMedia` so desktop keeps using `:hover`. Attach to the title wrapper, not the `<a>` (the theme often sets `pointer-events:none` on the submenu link).
- **Align breakpoints.** If the theme's desktop dropdown starts at `min-width:1200px` but your mobile rules use `≤991px`, the 992-1199px band has neither — a dead zone. Match toggle/burger visibility to the theme's actual breakpoint (`≤1199.98px`).
- **Verify across widths.** `getComputedStyle(submenuUl).display` at rest is `none` (correct); test the real hover (desktop) and a real toggle click (mobile). Parse the theme CSS *with @media context* — a flat grep hides which rules are media-gated.

---

## Validation checklist
- [ ] CND has no properties (data comes from JCR tree at render time)
- [ ] Helper functions handle all 4 nav item types: jnt:page, jnt:navMenuText, jnt:nodeLink, jnt:externalLink
- [ ] 3 levels rendered: level1 → level2 dropdown → level3 fly-out
- [ ] Language switcher uses `getSiteLocales()` — not hardcoded array
- [ ] Active link detection via inline `<script>` with `data-nav-path` attribute matching
- [ ] Mobile toggle via `data-mobile-nav-toggle` — SiteHeader sets it, nav reads it
- [ ] Resource bundle has label + ui.tooltip for the component
- [ ] `yarn build && yarn jahia-deploy` — component appears in Jahia content picker

## Transcribe the reference header DOM 1:1 — the imported CSS depends on it

The imported theme's header is laid out with **CSS grid named areas** (e.g. `.header-navigation>.component-content .grid{grid-template-areas:"logo infos ctas" "menu menu menu"}`), and the cells are selected by **exact markup** the tokenizer captured: `a[title="Header-Navigation 1"]` → `grid-area:logo`, `.title-headline` → infos, `.cta-area` → ctas, `.navigation-main` → menu. If you invent your own header structure, nothing lands in the right cell and the layout collapses (logo crammed, CTAs floating, header height 0). **Read the cached reference `.header-navigation` block and transcribe its DOM exactly**, substituting only dynamic data. Specific things that bite:
- Logo must be `<a title="Header-Navigation 1"><div class="logo"><img class="img-responsive"></div></a>` — the `.logo` class on an inner div, not the `<a>`; the `a[title=...]` selector is what assigns `grid-area:logo`.
- CTA buttons: `<a><div class="cta-2"><i.../><div class="field-cta-title-2">…</div></div></a>` (and `cta-1`). A bare `<div>{label}</div>` gets none of the button styling.
- Submenu dropdown: each `<li class="level1 itemN odd/even first/last rel-level1 submenu">` with the panel as a **direct child** `<ul class="clearfix">`. The dropdown panel needs an explicit white `background` (use `!important` — the theme sets a dark bg that wins otherwise) and `position:absolute`; the **right-most** item must open leftwards (`right:0;left:auto`) or it pins to the viewport edge.
- The language switcher belongs in the **top bar only** — do not also render it in the nav (it shows as a stray block below the menu).
- Font Awesome **Pro** icons (`fa-regular fa-store`, `fa-ticket-simple`) render as empty boxes against the free CDN; use the free **solid** equivalents (`fa-solid fa-store`, `fa-solid fa-ticket`). `fa-brands` (socials) are free and work.
