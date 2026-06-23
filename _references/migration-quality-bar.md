# Migration Quality Bar

Every skill in jahiaMigration produces output that must meet this bar before the user is told the task is done.

---

## HTML fidelity

- Zero layout regressions vs the reference site at 1440px and 375px.
- All CSS classes from the original HTML are present in the Jahia TSX (either as CSS Module keys or as imported vendor class strings).
- All `data-*`, `aria-*`, `id`, `role`, `<source>`, `<noscript>` attributes preserved verbatim.
- Interactive components (carousels, sliders, tabs, accordions) use Island architecture in render mode and flat fallback in edit mode.

## CND completeness

- Every user-facing string/text/richtext field has `i18n`.
- Every contributor-facing link uses `j:linkType (string, choicelist[linkTypeInitializer])`.
- No custom `tags` or `category` properties — use `jmix:tagged` and `category[autoSelectParent=false]`.
- Every resource bundle field key has a companion `.ui.tooltip` key.
- `mix:title` as supertype — never explicit `jcr:title` property.
- All props in `types.ts` use `?:` (optional).

## Navigation

- 3 levels rendered: L1 (top bar), L2 (dropdown), L3 (fly-out or sub-dropdown).
- All 4 nav item types supported: `jnt:page`, `jnt:navMenuText`, `jnt:nodeLink`, `jnt:externalLink`.
- `getNavItems` filter excludes `jmix:navMenu` containers.
- Language switcher uses `getSiteLocales()` — never hardcoded locale codes.

## Accessibility (WCAG 2.1 AA)

- Dropdown triggers have `aria-haspopup="true"` and `aria-expanded` reflecting open state.
- Active nav item uses `aria-current="page"`.
- Escape closes dropdowns and returns focus to trigger.
- Color contrast ≥ 4.5:1 for normal text, ≥ 3:1 for large text.
- All images have `alt` (empty string for decorative).

## Build and deploy

- `yarn build` exits 0 with no TypeScript errors.
- `yarn jahia-deploy` uploads successfully.
- Docker logs show `Registered Jahia component` for every new view.
- Existing pages still render after deploy (no regressions).

## Content

- All pages published (not just saved to default workspace).
- Content created in the correct site and language.
- Category and tag assignments use Jahia built-in taxonomy nodes — not string values.

## Listings (news / articles / press / white papers)

- List-type sections (actualités, news, articles, livres-blancs, press, agenda) are
  **structured `jmix:mainResource` content stored under `/sites/<site>/contents/...`**,
  each with its own `fullPage` view (own URL) — **never** inline `editorialBlock`s on
  the listing page.
- The listing page renders them via a **`jcrQuery`** view that queries the content
  type, shows a **card grid**, and (matching most reference sites) a **category/theme
  filter** (built from `jmix:categorized` categories) and a **"Voir plus"** load-more.
  Reference impl: `jcrQuery` view `newsGrid` (server + `newsGrid.client` island) +
  `newsArticle` (`jmix:mainResource, jmix:categorized`) `card`/`fullPage` views.
- Articles carry real `title`/`excerpt`/`body`/`publishDate`, a `thumbnail`
  WEAKREFERENCE, and ≥1 category.
- **Every new component view must ship CSS.** A view with semantic class names but no
  CSS renders as a full-width unstyled stack (the actualités failure mode). Verify the
  rendered grid/layout with a screenshot, not just presence of cards.

### Runbook — populating a listing with REAL content (replayable)

1. Capture the reference listing's article inventory with the **browser** (Chrome MCP):
   one `slug + image-path + title` per item. The reference is Cloudflare-protected, so
   only the browser can read it; on a block, **re-navigate 2–3 times** until it clears.
2. For each article, `navigate` to its page + `get_page_text` (full body is returned
   un-truncated, unlike `javascript_tool` which truncates ~1500 chars). Structure the
   real title / lead (excerpt) / body (`<p>`/`<h2>`/`<ul>`/`<ol>`) into the manifest.
3. Manifest: `orchestration/news/<project>.json` — `{ base, folder, articles:[{ name,
   slug, image (path rel. to base), imgFile (DAM filename), title, excerpt, date,
   body:[html blocks] }] }`. (`done:true` / missing `title` ⇒ skipped, so it runs
   incrementally — run it after every few captures to lock progress into Jahia.)
4. Run `python3 orchestration/news/migrate_news.py <project> <siteKey> <ns> <locale>`.
   It is **MCP-only**: `media.upload.url` (image import) → `content.create`/`update`
   (with `locale` for i18n props + `thumbnail` weakref) → `publication.publish`.
5. Delete fabricated/placeholder articles that don't map to real ones. Published nodes
   reject `content.delete` → use `content.mark_for_deletion` then publish each node
   individually (publishing the parent folder does **not** always propagate the
   deletion). Sweep the whole site, not just `contents/news` — orphans live elsewhere
   (e.g. `contents/tendances/*`).
6. Verify: EDIT and LIVE `select * from [<ns>:newsArticle]` counts match and equal the
   real count; every node has `title`(fr) + `body`(fr) + `thumbnail` refNode; a card
   image HEAD-fetches `200 image/*`. `naturalWidth==0` on off-screen cards is just
   `loading="lazy"`, not a broken image.

### MCP-publish rule (HARD — applies to ALL i18n content)

- **MCP is mandatory and first; GraphQL is a last-resort fallback only.**
- Set i18n properties with the MCP tool's **`locale`** param (`content.create`/
  `content.update`/`content.translate`). **Never** write `j:translation_<lang>` directly.
- Publish with **`publication.publish {languages:[...]}`**. **Never** use GraphQL
  `mutateNode{publish}` for translated content — it skips the `j:translation_<lang>`
  subnode, so the French text silently never reaches LIVE even though the write
  "succeeded". This bug masquerades as stale/missing content on the public site.

## Media / Images (non-negotiable)

- Every image is imported into the Jahia DAM and referenced by a **WEAKREFERENCE**
  field (`image`/`backgroundImage`/`logo`/`photo`) — **never** a URL-string field
  (`imageExternalUrl`/`backgroundImageUrl`/`logoExternalUrl`). The probe
  `orchestration/probes/no-url-images.sh <project> <siteKey> <ns>` must PASS.
- Images are imported with MCP **`media.upload.url`** (consistent UUID across
  default+live so the weakreference resolves), NOT the `import-image` servlet
  (mismatched UUIDs break weakreferences in live).
- Image URLs are captured from the reference site with a **browser** (Chrome MCP);
  the headless agent cannot fetch the bot-blocked source.
- Every page that has a hero shows its banner (hero image returns HTTP 200).
- Canonical tools: `orchestration/images/set_hero_refs.py` and `set_image_refs.py`
  (both take `<project> <siteKey> <ns>`).

## Layout

- Body content is centered in a max-width container with margins; heroes/banners
  stay full-bleed. The loaded theme overrides Bootstrap `.container` to
  `max-width:100%`, so a per-component `max-width` rule in `Layout.tsx` is required.
  Verify with element measurements (getBoundingClientRect) across MULTIPLE pages,
  never extrapolate from one.

## i18n

- EN and FR keys present for every field in `.properties` and `locales/`.
- No raw key strings visible in the rendered page (means a translation is missing).
- `loadNamespaces('module-name')` called before any UI extension registers.
