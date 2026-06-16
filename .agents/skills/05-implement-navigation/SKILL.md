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

## CND definition

`MainNavigation` has no editable properties — all data comes from the JCR page tree at render time:

```cnd
// src/components/Navigation/MainNavigation/definition.cnd
[ns:mainNavigation] > jnt:content, nsMix:pageComponent
```

That's it. No fields needed.

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

## Validation checklist
- [ ] CND has no properties (data comes from JCR tree at render time)
- [ ] Helper functions handle all 4 nav item types: jnt:page, jnt:navMenuText, jnt:nodeLink, jnt:externalLink
- [ ] 3 levels rendered: level1 → level2 dropdown → level3 fly-out
- [ ] Language switcher uses `getSiteLocales()` — not hardcoded array
- [ ] Active link detection via inline `<script>` with `data-nav-path` attribute matching
- [ ] Mobile toggle via `data-mobile-nav-toggle` — SiteHeader sets it, nav reads it
- [ ] Resource bundle has label + ui.tooltip for the component
- [ ] `yarn build && yarn jahia-deploy` — component appears in Jahia content picker
