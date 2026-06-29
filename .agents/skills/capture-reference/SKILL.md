---
name: capture-reference
description: Capture the REAL rendered content of the reference site (browser-first) before modeling or creating content. For JS/WAF sites the wget cache is incomplete — the listings, facet values, article bodies and image URLs load via JS. Fabricating from the cache is the #1 source of wrong content. Run during analysis (phase 1) and again before content creation (phase 9).
type: technical
phase: 1
status: active
allowed-tools: Bash, Read, Write
---

# Skill: Capture reference (browser-first)

## Why this exists

The most expensive failures in a migration are **fabricated content**: wrong
article bodies, wrong titles, wrong images, a missing item, invented taxonomy.
They happen when the agent builds from the **wget/curl cache** — but for any
modern site the cache is only the *static shell*. The parts that matter most are
loaded by JS and are **not in the cache**:

- listing/search results (news cards, product grids) — rendered by SXA search
- facet / filter values + counts (Thèmes, Type, …) — fetched from a search API
- full article bodies — sometimes, paginated or lazy
- the real image URLs behind each card
- the **complete item list** (the cache may show 2 of 5 articles)

And many sites sit behind a WAF (Cloudflare) that blocks `curl`/`WebFetch`
server-side. **The browser is the source of truth and the WAF fallback** — use
it FIRST for dynamic sites, not last.

> **Rule (anti-hallucination contract #2):** never invent content / titles /
> taxonomy / images. Capture them from the live site via the browser. If the
> browser can't reach a page either, **halt and ask the operator** — do not guess.

## When to run

- **Phase 1 (analyze):** capture every page's rendered text + image URLs + facet
  values, so the manifest + `content-data.json` are built from truth.
- **Phase 9 (create content):** re-capture each page right before filling it, so
  bodies/titles/dates/images match the original exactly.

Detect that you need this: if the wget cache page is missing the cards/listing
the live site shows, or `curl` returns a Cloudflare/JS-only shell, the cache is
incomplete → use the browser.

## How — Chrome MCP techniques that work

The browser tools (`mcp__Claude_in_Chrome__*`) drive the operator's real Chrome,
which is already past the WAF.

1. **Navigate + full article text** — `get_page_text` returns the clean article
   body (the whole thing, not just what fits a JS-eval display limit). Use it per
   detail page:
   ```
   navigate <article url>
   get_page_text <tabId>           # → real title + full body, all sections
   ```
   Save each to `projects/<project>/.reference/captured/<slug>.txt` (check it
   isn't already there first — reuse if so).

2. **Listing + the COMPLETE item list** — on the listing page, wait for the JS
   search to populate, then `javascript_tool` to extract every card's slug,
   image filename, and category labels:
   ```js
   const strip = u => (u||'').split('?')[0];
   [...document.querySelectorAll('a[href*="/news/"]')].map(a=>{
     const c=a.closest('[class*=result],[class*=card],article,li')||a;
     const img=c.querySelector('img');
     return {href:strip(a.getAttribute('href')),
             img:img?strip(img.src).split('/').pop():null,
             type:(c.querySelector('.label-type')||{}).textContent?.trim(),
             theme:(c.querySelector('.label-theme')||{}).textContent?.trim()};
   })
   ```
   This is how you discover items the cache never had (e.g. a 5th article).

3. **Facet / taxonomy values + counts** — read the filter dropdowns to model them
   as Jahia **categories** (see `06-implement-jcr-query`):
   ```js
   [...document.querySelectorAll('.facet-dropdown, select')].map(f=>({
     title:f.querySelector('.facet-title')?.textContent?.trim(),
     opts:[...f.querySelectorAll('option,li')].map(o=>o.textContent.trim())
   }))   // → "Le salon (5)", "Actualité (4)", "Le saviez-vous ? (1)"
   ```

4. **Real image URLs** — capture the `/-/media/...` path of every card/hero
   image. Then import them server-side with the image-proxy, which **reaches the
   WAF'd CDN even when page-fetch is blocked**:
   ```bash
   curl -s -u $JAHIA_USER -H "Origin: $JAHIA_HOST" -X POST \
     "$JAHIA_HOST/modules/jahia-image-proxy/import-image" \
     --data-urlencode "sourceUrl=https://<site>/-/media/.../pagani.jpg" \
     --data-urlencode "destPath=/sites/<site>/files/imported/<folder>" \
     --data-urlencode "filename=pagani.jpg"
   ```

## Gotchas

- **JS-eval output is display-truncated** (~1.5 KB). For long bodies use
  `get_page_text` (returns the whole article); for structured data return compact
  JSON, or write per-page to disk rather than one giant blob.
- **The privacy filter blocks output containing query strings** — `strip()` the
  `?...` off URLs before returning them from `javascript_tool`.
- **Transport long content back via GraphQL variables** (`$b:String!`), not
  string-interpolated mutations — avoids escaping accents/quotes/® and the filter.
- Wait for the JS search to populate (the cards appear a few seconds after the
  facets) before extracting the item list.

## Output — persist into the PER-PROJECT cache (never re-fetch / re-drive Chrome)

Write captured truth under **`projects/<project>/.reference/`** — the same
per-project cache the curl scraper uses — so a re-run reuses it instead of
re-driving the browser:
- `projects/<project>/.reference/captured/<slug>.txt` — rendered body per page
  (gitignored, like `.reference/cache/`)
- `projects/<project>/.reference/items.json` — the complete list (slug, title,
  image URL, categories, date) — **committed**
- `projects/<project>/.reference/facets.json` — each facet's values + counts —
  **committed**

> **Reuse rule:** before any curl OR browser capture, check
> `projects/<project>/.reference/` (`cache/` for curl hits, `captured/` +
> `items.json`/`facets.json` for browser captures). A hit is reused; never
> re-hit the origin or re-drive Chrome for something already captured.

These feed `content-data.json` and the content-creation step. **A page's content
is not "modelled" until it was captured from the live source, not remembered.**
