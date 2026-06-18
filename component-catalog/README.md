# Component Catalog

Proven, reusable Jahia component implementations from past migrations. Before building a new component from scratch, check here first.

## How to use

1. Find the component by its CSS class signature (the dominant class from the reference site HTML)
2. Copy the implementation files into your project, updating the namespace prefix
3. Adapt the CND fields if needed — the HTML structure and CSS classes should not change

## How to add

After a migration is complete and a component passes the visual diff gate, add it here:
1. Copy `definition.cnd`, `default.server.tsx`, and optionally `fullPage.server.tsx` into a subfolder named after the CSS class
2. Fill in the catalog entry below
3. Include the source site and the reference URL so future agents can compare

---

## Catalog

### `banner-title3 small-banner` — Sub-page hero banner
- **Source:** SIAL Paris migration (2026-06)
- **Reference:** `https://www.sialparis.com/fr-FR/temps-forts/sial-innovation`
- **Files:** `banner-title3/`
- **Views:** `default` only (page area component, no full-page URL)
- **Key fields:** `jcr:title` (h1 overlay), `subtitle` (watermark text), `backgroundImage` (weakreference)
- **Notes:** Background image is mandatory — without it the banner renders as a plain colored bar

### `img-content-block-l` — 2-column image + text block
- **Source:** SIAL Paris migration (2026-06)
- **Reference:** `https://www.sialparis.com/fr-FR/temps-forts/sial-innovation`
- **Files:** `img-content-block-l/`
- **Views:** `default` only
- **Key fields:** `watermarkWord`, `heading`, `bodyText` (richtext), `image` (weakreference), `j:linkType` CTA
- **Notes:** Image is always on the left at desktop. The `-l` suffix in the class means "image left". A `-r` variant exists on the reference site (image right) — not yet implemented.

### `pages-pushes hover` — Push cards grid (4-column)
- **Source:** SIAL Paris migration (2026-06)
- **Reference:** `https://www.sialparis.com/fr-FR/temps-forts/sial-innovation`
- **Files:** `pages-pushes/`
- **Views:** parent `default` + child `sialp:pagesPushesItem` `default`
- **Key fields (parent):** `heading`; **Key fields (child):** `jcr:title`, `description`, `image`, `j:linkType`
- **Notes:** Child items MUST use a dedicated view (`item.server.tsx`) with `<Render node={child} />` in the parent — direct `getPropertyAsString` fails for i18n properties on child nodes. Each child needs `col-md-3 col-sm-6` on its root div.

### `date-lieu-horaires` — 3-column info cards with icon watermarks
- **Source:** SIAL Paris migration (2026-06)
- **Reference:** `https://www.sialparis.com/fr-FR/infos-pratiques/dates-et-acces`
- **Files:** `date-lieu-horaires/`
- **Views:** container `default` + child `sialp:infoCard` `default`
- **Key fields (child):** `iconClass` (Font Awesome class string), `title`, `body` (richtext)
- **Notes:** The large watermark icon is a decorative FA icon behind the text. Requires FA to be loaded.

---

## Adding components from a new migration

After completing a migration and passing `/12-visual-diff` with 0 critical gaps, run:

```bash
# Copy proven components into catalog
MIGRATION_DIR="projects/<module-name>/src/components"
CATALOG_DIR="component-catalog"

for component in PageHero ImgContentBlock PagesPushes DateLieuHoraires; do
  src="$MIGRATION_DIR/Content/$component"
  if [ -d "$src" ]; then
    css_class=$(grep -r "className" "$src" | grep -oP '"[a-z][a-z-]+ [a-z][a-z-]+"' | head -1 | tr -d '"')
    dest="$CATALOG_DIR/$css_class"
    mkdir -p "$dest"
    cp "$src"/*.cnd "$src"/*.tsx "$src"/*.css "$dest/" 2>/dev/null
    echo "Catalogued: $component → $dest"
  fi
done
```
