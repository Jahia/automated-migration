---
name: 9b-populate-shell
description: Populate the shared site shell (navigation / footer / top-bar AbsoluteAreas on the home page) with child content from the captured reference, via the Jahia MCP server. Focused sub-skill of 09-create-content for the generated shell story.
type: content
phase: 9
status: active
depends_on:
  - 8-page-templates
allowed-tools: Bash, Read, WebFetch
---

# Skill: Populate the site shell (focused)

You are populating **only the shared shell regions**: the AbsoluteArea containers the
page templates place on the home page (typically navigation, footer, top bar — read
the template source or `page.structure` to see which exist for THIS module; do not
assume names). Page `main` areas are owned by other stories — do not touch them.

## Why this story exists (AbsoluteArea-needs-children)

Shared regions render in the Page Builder edit canvas ONLY if their container node has
child content nodes. Zero children = blank in edit mode (even when live looks fine).
So every shell container must hold real, contributed child nodes mirroring the
reference: social links, footer link columns, CTA buttons, contact lines, etc.

## Scope boundaries (containment)

- **IN**: the AbsoluteArea container nodes on the home page + their children; publish.
- **OUT — never touch**: any page `main` area; module source code; mainResource
  content; pages other than where the shell containers live.

## Method

1. **Discover the shell containers** — `page.structure` on the home page; identify the
   absolute-area containers and their allowed child types (`content.type` on the
   container's nodeType, and the manifest's `areaType: "absolute"` components).
2. **Idempotency first** — `content.list` each container. Reuse/update existing
   children; never duplicate, never delete published nodes.
3. **Mirror the captured reference** — the shell markup in the captured pages
   (`projects/<project>/.reference/`) + the extracted shell instances in
   `orchestration/content/<project>.content-load.json` (they appear on every captured
   page; use any page's copy) define exactly which links, labels and icons exist.
   Verbatim text; no invented items.
4. **Navigation** — the main menu renders from the JCR page tree (never hardcoded
   links). Its container children are only the EXTRAS the reference shows (e.g. a CTA
   button); the tree itself comes from pages. If the reference nav has 3 levels, the
   pages must provide them — report missing pages in `risks`, do not fake menu items.
5. **Links are contributed** — every shell link uses `j:linkType`
   (`internal` + `j:linknode`, or `external` + `j:url`). Both targets are **i18n**:
   set them **with the `locale` param** or MCP silently no-ops (blank link).
   Logos/icons: DAM weakreferences from `orchestration/images/<project>.imported.json`
   — never URL strings.
6. **Publish** each container subtree, then render-gate: the home page's live render
   AND edit frame must show the populated shell.

## MCP quick reference

Same transport as all content stories — JSON-RPC 2.0 POST to
`http://localhost:8080/modules/mcp` (creds from the project `.env`):
`page.structure`, `content.list`, `content.type`, `content.create` (supports atomic
`children`), `content.update` (**needs `locale` for links/weakrefs**),
`publication.publish`. Never guessed GraphQL.

## Definition of done

- Every shell container has the reference's children (verbatim labels, wired links,
  DAM logos) and is published.
- The home page renders the shell in live AND in the edit frame (no blank regions).
- The step's probes pass; anything not reproducible is reported in `risks`.
