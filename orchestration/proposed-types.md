# Gap analysis - new component types for the expanded sial-paris sitemap

> STATUS (resolved): the 3 type-families below were BUILT and deployed; baseline
> re-snapshotted to 47 types. `formEmbed` was DROPPED - SIAL's contact/whitepaper
> forms are external links (bit.ly, typeform.com), so they reuse `ctaBanner`.
> The `partnersList` category extension + `tabbed` view were added. The reuse
> guard now passes, so the loop's content phase runs without halting on types.


Scanned the new reference pages (via Chrome, 2026) against the 41 baseline
`sialp:` types. The editorial/landing pages reuse existing types. The functional
pages need a small, bounded set of NEW types - each reused across several pages.

## New types to add (4 type-families, ~7 nodes)

| Proposed type(s) | Pattern | Driven by pages | Existing match? |
|---|---|---|---|
| `sialp:faqSection` + `sialp:faqItem` | Accordion of Q&A | faq, tarifs-visiteurs (conditions, visa), VIP-ticket (FAQ) | none |
| `sialp:pricingTable` + `sialp:pricingTier` | Price matrix (period x audience) and the VIP-vs-Visiteur feature comparison (same table type, different view) | tarifs-visiteurs, VIP-ticket | none |
| `sialp:peopleGrid` + `sialp:personCard` | Photo + name + role + bio/contact link | contacts (commercial team), SIAL-Insights-2024 (expert authors), SIAL-Talks / SIAL-Summits (speakers) | none |
| `sialp:formEmbed` (conditional) | Lead-gen / contact / whitepaper-download form | contacts, SIAL-Insights-2024 | none - only if forms are embedded; if they link out to a Comexposium form, reuse `ctaBanner` instead |

## Extend an existing type (no new type)

| Type | Change | Driven by |
|---|---|---|
| `sialp:partnersList` / `partnerEntry` | add a category facet + a tabbed/filtered view (ANIMATIONS, INSTITUTIONNELS, MEDIAS, SALONS, SIAL INSIGHTS) | nos-partenaires; SIAL-Talks partners reuse the plain list |

## Confirmed reuse (no change) - the rest of the tree

- Sub-page banners -> `pageHero`
- Prose / 2-col / vertical-image editorial -> `editorialBlock` (default/rightImg/verticalImage), `imgContentBlock`, `richTextBlock`, `introText`, `leadText`
- "X reasons / advantages" blocks -> `featureList` / `featureItem`
- CTAs and ticket banners -> `ctaBanner`, `ctaDualCards`
- News (tendances/actualites) -> `newsListing` / `newsArticle` (default/card/fullPage)
- Sectors (les-secteurs-du-salon, /boissons-sans-alcool) -> `sectorsSection` / `sectorItem`
- Trends (tendances, focus, /proteines) -> `trendsSection` / `trendCard`
- Partners logos/carousel -> `partnersCarousel`, `partnersList`, `partnerLogo`
- Structural -> `gridRow`, `jcrQuery`, `simpleTitle`, `previousNext`

## Recommendation

Build the 4 families above BEFORE the loop's content phase so it runs halt-free,
then re-snapshot the baseline:
`bash orchestration/probes/inventory.sh projects/sial-paris sialp --write orchestration/component-baseline.txt`

`formEmbed` is the only uncertain one - decide after confirming whether SIAL's
forms are embedded or external links.
