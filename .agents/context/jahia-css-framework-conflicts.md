# CSS Framework Conflict Patterns

Patterns encountered when importing CSS from a live site into a Jahia module static directory. Always run the detection checks in skill 03 (import-assets) before implementing components.

---

## Font Awesome Pro vs Free

**Symptom:** Icons render as blank boxes or missing glyphs after import.

**Root cause:** The source site uses Font Awesome Pro (paid kit). The CSS bundle (e.g. `core-libraries.css`) declares `font-family: "Font Awesome 6 Pro"` as the icon font family, but the actual Pro `.woff2` files are not publicly downloadable. Adding a CDN link for FA Free does not help — the browser resolves glyphs using the `font-family` name exactly, so it looks for a `@font-face` block named `"Font Awesome 6 Pro"`.

**Detection:**
```bash
grep -r "Font Awesome 6 Pro\|Font Awesome 6 Sharp\|fa-pro\|font-awesome.*pro" static/css/ | head -20
```

**Fix:** Add `@font-face` remapping in `Layout.tsx` AFTER all `<AddResources>` CSS imports, pointing the Pro family names to FA Free CDN woff2 files:

```tsx
<style dangerouslySetInnerHTML={{ __html: `
  @font-face { font-family: "Font Awesome 6 Pro"; font-weight: 900; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2"); }
  @font-face { font-family: "Font Awesome 6 Pro"; font-weight: 400; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-regular-400.woff2") format("woff2"); }
  @font-face { font-family: "Font Awesome 6 Brands"; font-weight: 400; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-brands-400.woff2") format("woff2"); }
  @font-face { font-family: "Font Awesome 6 Sharp"; font-weight: 900; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2"); }
` }} />
```

**Why after AddResources:** The `@font-face` block must override any `src:` declaration already in the imported CSS for the same family name. CSS cascade order matters — later declarations win.

---

## CSS Grid header layouts (Sitecore SXA, custom frameworks)

**Symptom:** Navigation component renders at full viewport width (e.g. 2505px) or completely outside the header area.

**Root cause:** The source site header uses CSS Grid (`display: grid; grid-template-columns: 300px auto 152px`) with named areas. The `navigation-main` element is assigned `grid-area: 2/2/3/4`. If the Jahia view only outputs `<div class="navigation-main">` without a `.grid` parent, the browser finds no grid context and the element falls into normal block flow.

**Detection:**
```bash
grep -n "grid-area\|grid-template-columns" static/css/*.css | head -20
grep -n "navigation-main\|\.grid\b" static/css/*.css | head -20
```

**Fix (Pattern B — full-header pattern):** The `ns:mainNavigation` view must output the **complete header structure**: the `<header>` element, the `.grid` container, ALL grid items (logo, dates headline, ticket CTA, navigation). They must all live in the same view because they share a grid parent.

```tsx
return (
  <header>
    <div className="grid">
      <a href={buildNodeUrl(homePage)}><img src={logoSrc} /></a>   {/* col 1 row 1 */}
      <div className="title-headline">...</div>                    {/* col 2 row 1 */}
      <div className="cta-area">...</div>                         {/* col 3 row 1 */}
      <div className="navigation-main">                           {/* col 2-3 row 2 */}
        <nav><ul>{/* JCR page tree */}</ul></nav>
      </div>
    </div>
  </header>
);
```

**Key decision:** If skill 01 (analyze-website) identified logo and CTAs as separate components, but the CSS grid ties them together in the header — consolidate them into the `ns:mainNavigation` view. The grid constraint overrides the conceptual separation. Add CND fields to `ns:mainNavigation` for any configurable items (logo image weakreference, CTA label, CTA link).

---

## JavaScript initialization classes (`.initialized`, `.swiper-initialized`)

**Symptom:** Carousel or slider renders statically (all slides visible, no controls) even though the JS library is loaded.

**Root cause:** Libraries like Swiper, Swiffy Slider, and custom carousels check for a CSS class on the wrapper (e.g. `.initialized`, `.swiper-initialized`) before activating. If the class is present in the HTML from the source site, the library assumes it already ran and skips initialization.

**Detection:**
```bash
grep -n "initialized" static/css/*.css | head -10
grep -rn "\.initialized\b" static/css/*.css | head -10
```

**Fix:** Do NOT add `initialized` or `swiper-initialized` to the TSX output. Let the JS library add it after it runs. Only hardcode structural classes (`carousel`, `slider-container`, `slides`, etc.), never state classes that JS manages.

---

## Bootstrap version collisions

**Symptom:** Grid layouts or utility classes behave unexpectedly after import (wrong gutters, wrong breakpoints).

**Root cause:** The source site may use Bootstrap 4 while a Jahia-provided stylesheet uses Bootstrap 5 (or vice versa). The two versions have incompatible grid APIs (`col-md-4` vs `col-md-4`, but `offset-md-2` vs `col-md-offset-2`).

**Detection:**
```bash
grep -n "bootstrap\|Bootstrap" static/css/*.css | head -5
grep -n "\.col-xs-\|\.offset-md-\|\.col-md-offset-" static/css/*.css | head -5  # Bootstrap 3/4 indicators
```

**Fix:** Import only the specific Bootstrap version used by the source site. Do not mix versions. If the source uses BS4 and you need a Jahia base, check whether `bootstrap4.css` is already in the Jahia module static CSS output before importing again.
