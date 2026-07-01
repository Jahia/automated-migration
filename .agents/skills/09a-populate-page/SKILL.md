---
name: 9a-populate-page
description: Populate ONE small slice of pages (<=3) with content from the captured reference, via the Jahia MCP server. Focused sub-skill of 09-create-content for generated per-slice stories. Publishes everything it creates.
type: content
phase: 9
status: active
depends_on:
  - 8-page-templates
allowed-tools: Bash, Read, WebFetch
---

# Skill: Populate a page slice (focused)

You are populating **only the pages named in your step's `pages` input** — nothing else.
This is one contained story: other slices, the shared shell (nav/footer/topBar), and
mainResource content are handled by other stories. Stay in scope.

## Scope boundaries (containment)

- **IN**: the pages in `inputs.pages` — their `main` area content, images, links, publish.
- **OUT — never touch**:
  - any page not in `inputs.pages`
  - the shell AbsoluteAreas (navigation / footer / top bar) — owned by the shell story
  - `jmix:mainResource` nodes (articles, events, press releases) — they live in
    `jnt:contentFolder`s, created by a deterministic loader story. NEVER create them
    inline in a page `main` area. A listing page gets ONE query/listing component;
    its `startNode` is wired later by a deterministic story — leave it unset.
  - module source code. If a component type is missing or broken, report it in
    `risks` and fail the step — do not patch views mid-content.

## Inputs you consume (files on disk — read them, do not improvise)

| File | What it gives you |
|---|---|
| `projects/<project>/workflow-output/component-manifest.json` | nodeTypes available, their fields, container/children shape |
| `orchestration/content/<project>.content-load.json` | per-page extracted instances: REAL text/fields per component, in document order |
| `orchestration/images/<project>.imported.json` | per-page imported DAM assets: `file` -> `jcrPath` (the weakref target) |
| `projects/<project>/.reference/` captured pages | ground truth for ordering and anything ambiguous |

## Method (per page, in order)

1. **Discover before creating** — `page.structure` for the page; `content.list` on its
   `main` area. IDEMPOTENT: if a node for a reference section already exists, update
   it; never duplicate, never delete published content.
2. **Mirror the reference order** — create one module component instance per reference
   section, in document order, using the extracted fields from content-load.json
   verbatim (no invented text, no placeholder lorem).
3. **Images are DAM weakreferences** — resolve `file` -> `jcrPath` via imported.json and
   set the component's weakref property (usually `image`) + its alt text. NEVER store a
   URL string in any property.
4. **Links** — `j:linknode` / `j:url` are **i18n**: set `j:linkType` first, add the
   `jmix:internalLink`/`jmix:externalLink` mixin, then set the target **with the
   `locale` param** — without it MCP silently no-ops and the CTA renders nothing.
   Internal pages use `internal` + `j:linknode` (never an external URL to an internal page).
5. **Publish** — publish the page subtree after populating it (`publication.publish`
   with the step's language(s)). Writes go to default; visitors see live.
6. **Render-gate as you go** — after each page, confirm the live render is non-empty
   before moving to the next page of the slice.

## MCP quick reference (the only transport — never guessed GraphQL)

All calls: JSON-RPC 2.0 POST to `http://localhost:8080/modules/mcp` (`-u` from the
project `.env`; default `root:root`).

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"TOOL","arguments":{ ... }}}' | python3 -m json.tool
```

| Tool | Use |
|---|---|
| `page.structure` | areas + allowed types of a page |
| `content.list` | children of an area (idempotency check) — `{parentPath, locale}` |
| `content.type` | properties of a nodeType — `{nodeType}` |
| `content.create` | `{parentPath, nodeType, properties, locale[, name, children]}` — children lets a container + its items be one atomic call |
| `content.update` | `{path, properties, locale}` — **silently no-ops weakrefs/links without `locale`**; verify with `content.get` after critical updates |
| `publication.publish` | `{path, languages:[...]}` |

Property rules: i18n and non-i18n share the same `properties` map (locale param resolves
them). Weakrefs accept an absolute JCR path. Multi-valued = JSON array. Dates = ISO-8601.

## Definition of done

- Every page in `inputs.pages` renders live with the reference's sections, real text,
  DAM-weakref images, and working links — and is published.
- The step's probes pass: `content.sh` (fidelity vs captured reference + real JCR
  state), `render-all.sh` (live render truth), `contract.sh` (inputs existed).
- Anything you could not reproduce faithfully is listed in `risks` — honestly.
