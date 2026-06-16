# Context — Jahia Taxonomy Patterns (Tags & Categories)

Tags and categories are **built-in Jahia taxonomy features** — they require no CND changes. They are available on any node via Jahia's own mixins. **Never re-define them in a CND file.**

---

## Key Concepts

| Feature | Mixin | Property | Value Type |
|---|---|---|---|
| Tags | `jmix:tagged` | `j:tagList` | `STRING` (multiple) |
| Categories | `jmix:categorized` | `j:defaultCategory` | `WEAKREFERENCE` (multiple) |

**Non-negotiable rules:**
- Never declare `j:tagList` or `j:defaultCategory` in a CND — they conflict with Jahia's built-in mixins and break faceted search and the category UI
- Categories reference **existing** nodes — they cannot be created inline with the content
- Always call `addMixins` before setting taxonomy properties
- Taxonomy is always a **post-creation step** — never set in `addChild`

---

## Part 1: Tags (`jmix:tagged` / `j:tagList`)

Tags are free-form strings. Any number can be assigned to a node.

### GraphQL Mutation

```graphql
mutation AddTags($path: String!, $tags: [String]!) {
  jcr {
    mutateNode(pathOrId: $path) {
      addMixins(mixins: ["jmix:tagged"])
      mutateProperty(name: "j:tagList") {
        setValues(values: $tags)
      }
      uuid
    }
  }
}
```

Pass `$tags` as an array: `["finance", "innovation", "digital-banking"]`

### Query Existing Tags

```graphql
query {
  jcr(workspace: EDIT) {
    nodeByPath(path: "/sites/mysite/home/news/article-1") {
      property(name: "j:tagList") { values }
      mixinTypes { name }
    }
  }
}
```

---

## Part 2: Categories (`jmix:categorized` / `j:defaultCategory`)

Categories are node references. They live exclusively under:

```
/sites/systemsite/categories/
```

> **Never** use `/categories/` or `/sites/{siteName}/categories/`. The category tree is global — always under `systemsite`.

### Step 1: Find Existing Categories

```graphql
query {
  jcr {
    nodeByPath(path: "/sites/systemsite/categories") {
      children {
        nodes {
          name uuid
          children { nodes { name uuid } }
        }
      }
    }
  }
}
```

### Step 2: Create Missing Categories

```graphql
mutation {
  jcr(workspace: EDIT) {
    addNode(
      parentPathOrId: "/sites/systemsite/categories"
      name: "digital-transformation"
      primaryNodeType: "jnt:category"
      properties: [
        { language: "en", name: "jcr:title", type: STRING, value: "Digital Transformation" }
      ]
    ) { uuid }
  }
}
```

Save the returned `uuid` — you need it to link content.

### Step 3: Link Categories to Content

```graphql
mutation AddCategories($path: String!, $categories: [String]!) {
  jcr {
    mutateNode(pathOrId: $path) {
      addMixins(mixins: ["jmix:categorized"])
      mutateProperty(name: "j:defaultCategory") {
        setValues(values: $categories)
      }
      uuid
    }
  }
}
```

Pass `$categories` as an array of UUID strings.

---

## Part 3: Both Tags and Categories Together

```graphql
mutation {
  jcr(workspace: EDIT) {
    mutateNode(pathOrId: "/sites/SITENAME/home/AREA/NODE") {
      addMixins(mixins: ["jmix:tagged", "jmix:categorized"])
      setPropertiesBatch(properties: [
        { name: "j:tagList", type: STRING, values: ["innovation", "strategy"] }
        { name: "j:defaultCategory", type: WEAKREFERENCE, values: ["uuid-of-category"] }
      ]) { path }
    }
  }
}
```

---

## Part 4: Rendering Categories in TSX

`j:defaultCategory` is a multi-value weakreference. **Do not call `getNode()` on it** — use `getValues()` and resolve each UUID via the session.

```tsx
const categoryLabels: string[] = [];
if (node.hasProperty("j:defaultCategory")) {
  try {
    const session = node.getSession();
    const values = Array.from(node.getProperty("j:defaultCategory").getValues());
    for (const val of values) {
      const catNode = session.getNodeByIdentifier(val.getString());
      const label = catNode.hasProperty("jcr:title")
        ? catNode.getProperty("jcr:title").getString()
        : catNode.getName();
      if (label) categoryLabels.push(label);
    }
  } catch { /* category may not be set */ }
}
```

```tsx
// ❌ WRONG — getNode() is for single-value reference properties only
const cat = node.getProperty("j:defaultCategory").getNode(); // throws on multi-value

// ✅ CORRECT — getValues() + session.getNodeByIdentifier()
const values = Array.from(node.getProperty("j:defaultCategory").getValues());
```

---

## Part 5: CND — Never Declare Taxonomy Properties

```cnd
// ✅ CORRECT — add jmix:categorized as a supertype mixin
[myns:myType] > jnt:content, jmix:categorized
 - title (string) i18n

// ❌ WRONG — declaring j:defaultCategory conflicts with the built-in mixin
[myns:myType] > jnt:content
 - j:defaultCategory (weakreference) multiple
```

---

## Part 6: Migration Pattern (TypeScript)

When migrating content from an external system with taxonomy data, always apply taxonomy as a **post-creation step**:

```typescript
// Step 1: Create the content node (standard flow)
const nodeUuid = await createContentNode(...);

// Step 2: Resolve category UUIDs
const categoryUuids = await resolveCategoryUuids(sourceCategories);

// Step 3: Apply taxonomy
await applyTaxonomy(nodeUuid, { tags: sourceTags, categoryUuids });

async function applyTaxonomy(nodePath: string, taxonomy: { tags?: string[]; categoryUuids?: string[] }) {
  const mixins: string[] = [];
  const properties: object[] = [];

  if (taxonomy.tags?.length) {
    mixins.push("jmix:tagged");
    properties.push({ name: "j:tagList", type: "STRING", values: taxonomy.tags });
  }
  if (taxonomy.categoryUuids?.length) {
    mixins.push("jmix:categorized");
    properties.push({ name: "j:defaultCategory", type: "WEAKREFERENCE", values: taxonomy.categoryUuids });
  }
  if (!mixins.length) return;

  await graphqlMutation(`mutation {
    jcr(workspace: EDIT) {
      mutateNode(pathOrId: "${nodePath}") {
        addMixins(mixins: ${JSON.stringify(mixins)})
        setPropertiesBatch(properties: ${serializeProperties(properties)}) { path }
      }
    }
  }`);
}
```

### Category Resolution Helper (with caching)

```typescript
const categoryCache = new Map<string, string>(); // name → uuid

async function resolveCategoryUuids(categoryNames: string[]): Promise<string[]> {
  const uuids: string[] = [];
  for (const name of categoryNames) {
    if (categoryCache.has(name)) { uuids.push(categoryCache.get(name)!); continue; }
    const uuid = await findCategoryByName(name) ?? await createCategory(name);
    categoryCache.set(name, uuid);
    uuids.push(uuid);
  }
  return uuids;
}
```

---

## Verification Query

```graphql
query {
  jcr(workspace: EDIT) {
    nodeByPath(path: "/sites/SITENAME/home/AREA/COMPONENT") {
      mixinTypes { name }
      property(name: "j:tagList") { values }
      property(name: "j:defaultCategory") { refNodes { uuid name displayName } }
    }
  }
}
```

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| `j:tagList` or `j:defaultCategory` declared in CND | Remove — they come from Jahia's built-in mixins |
| Setting taxonomy in `addChild` | Not supported — always use a separate `mutateNode` after creation |
| `value` instead of `values` for tags | Use `values: [...]` array |
| Referencing a non-existent category UUID | Create the category first, then link |
| Forgetting `addMixins` | Property is silently ignored — always call `addMixins` first |
| Using `/sites/{siteName}/categories/` | Always use `/sites/systemsite/categories/` |
| `getNode()` on `j:defaultCategory` | Use `getValues()` + `session.getNodeByIdentifier()` |
