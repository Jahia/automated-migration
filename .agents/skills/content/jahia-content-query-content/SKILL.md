---
name: jahia-content-query-content
description: Queries JCR content from a running Jahia instance via the GraphQL API. Use when asked to list, inspect, or retrieve content nodes, check what content exists, or audit a site's content.
---

# Skill: jahia-content-query-content

## MCP-first rule

**Always prefer the Jahia MCP server over GraphQL for content operations.** Check availability first:

```bash
curl -s http://localhost:8080/modules/mcp | python3 -c "import json,sys; d=json.load(sys.stdin); print('MCP OK -', len(d['tools']), 'tools')"
```

If MCP is available, use these tools instead of GraphQL:
- Explore structure: `content.type`, `site.types`, `page.structure`
- Query content: `content.list`, `content.search`, `content.get`, `page.list`
- Move/rename: `content.move`, `content.rename`, `content.reorder`
- Translate: `content.translate`

MCP call pattern:
```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"TOOL","arguments":{...}}}'
```

**Credentials: root / root** (NOT root/root1234 - that is wrong for local dev).

Only fall back to GraphQL when MCP is unavailable or a specific operation has no MCP equivalent.

---

Retrieves JCR content from a running Jahia instance using the GraphQL JCR query API.

---

## Prerequisites

- Jahia running at `http://localhost:8080`
- Credentials: `root` / `root` (default)
- GraphQL endpoint: `http://localhost:8080/modules/graphql`

**Auth pattern — always use both flags:**
```bash
curl -u root:root \
     -H "Content-Type: application/json" \
     -H "Origin: http://localhost:8080" \
     ...
```

> ⚠️ The `Origin: http://localhost:8080` header is **required**. Requests without it return `Permission denied` even with correct credentials.

---

## Query patterns

### 1 — Get a node by path

```bash
curl -s -u root:root \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8080" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query": "{ jcr { nodeByPath(path: \"/sites/mySite/contents/articles\") { children { nodes { name path primaryNodeType { name } } } } } }"
  }'
```

### 2 — Query by node type (JCR-SQL2)

```bash
curl -s -u root:root \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8080" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query": "{ jcr { nodesByQuery(query: \"SELECT * FROM [namespace:typeName] WHERE ISDESCENDANTNODE(\u0027/sites/mySite\u0027) ORDER BY [jcr:created] DESC\", queryLanguage: SQL2) { nodes { name path uuid } } } }"
  }'
```

### 3 — Read node properties (including i18n)

```bash
curl -s -u root:root \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8080" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query": "{ jcr { nodeByPath(path: \"/sites/mySite/contents/articles/my-article\") { name uuid properties(language: \"en\") { name value } } } }"
  }'
```

> ⚠️ **i18n properties require `language:` in the `properties()` call.** Without it, i18n properties are returned empty.

### 4 — Filter by property value

```bash
curl -s -u root:root \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8080" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query": "{ jcr { nodesByQuery(query: \"SELECT * FROM [namespace:article] WHERE [product] = \u0027jahia\u0027 AND ISDESCENDANTNODE(\u0027/sites/mySite\u0027)\", queryLanguage: SQL2) { nodes { name path } } } }"
  }'
```

### 5 — List all sites

```bash
curl -s -u root:root \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8080" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query": "{ jcr { nodesByQuery(query: \"SELECT * FROM [jnt:virtualsite] WHERE ISCHILDNODE(\u0027/sites\u0027)\", queryLanguage: SQL2) { nodes { name path } } } }"
  }'
```

### 6 — Check publication status

```bash
curl -s -u root:root \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8080" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query": "{ jcr { nodeByPath(path: \"/sites/mySite/contents/articles/my-article\") { name aggregatedPublicationInfo(language: \"en\") { publicationStatus } } } }"
  }'
```

Publication status values: `PUBLISHED`, `MODIFIED`, `NOT_PUBLISHED`, `UNPUBLISHED`, `MARKED_FOR_DELETION`

---

## JCR-SQL2 quick reference

```sql
-- All nodes of a type under a path
SELECT * FROM [ns:typeName] WHERE ISDESCENDANTNODE('/sites/mySite')

-- Direct children only
SELECT * FROM [ns:typeName] WHERE ISCHILDNODE('/sites/mySite/contents/articles')

-- Filter by property
SELECT * FROM [ns:typeName] WHERE [propName] = 'value'

-- Order by date (newest first)
SELECT * FROM [ns:typeName] WHERE ISDESCENDANTNODE('/sites/mySite') ORDER BY [jcr:created] DESC

-- Limit results (pass limit/offset as query params)
-- nodesByQuery(query: "...", queryLanguage: SQL2, limit: 10, offset: 0)
```

---

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Permission denied` | Missing `Origin` header | Add `-H "Origin: http://localhost:8080"` |
| i18n properties returned empty | `language:` not specified | Add `language: "en"` to `properties()` call |
| Node not found | Wrong path or node doesn't exist | Verify path with `nodeByPath(path: "/sites")` first |

---

## References

- Jahia GraphQL API: `http://localhost:8080/modules/graphql` (open in browser for interactive playground)
- JCR-SQL2 language spec: https://docs.adobe.com/content/docs/en/spec/jcr/2.0/6_Query.html
