# Context — CND Syntax Reference (Jahia 8.2)

CND (Compact Namespace and Node Type Definition) files define content types in Jahia. This guide provides complete syntax rules, all selectors and keywords, and production-validated examples from the Jahia QA test suite.

---

## Syntax Order — CRITICAL

The order of elements in a property definition is **strictly enforced**:

```
- propertyName (type, selector) = 'default' keyword1 keyword2 < constraint
  ──────┬──── ────────┬──────── ─────┬───── ────────┬──────── ─────┬─────
        1             2              3               4              5
```

1. **Property name**
2. **Type and selector** — in parentheses, comma-separated
3. **Default value** — with `=`, comes before keywords
4. **Keywords** — outside parentheses, after default
5. **Constraints** — with `<`, always last

---

## Property Types

| Type | Use for |
|---|---|
| `string` | Text, URLs, identifiers |
| `weakreference` | Reference to another node (safe: null if target deleted) |
| `date` | Dates stored as ISO 8601 |
| `boolean` | True/false flags |
| `long` | Integer numbers |
| `double` | Decimal numbers |
| `decimal` | High-precision decimals |
| `uri` | URI values |
| `name` | JCR name values |
| `path` | JCR path values |

---

## Selectors (complete list)

### Text
```cnd
- title (string)                                      # Plain text input
- notes (string, textarea)                            # Multi-line textarea
- content (string, richtext)                          # WYSIWYG editor
- password (string, text[password]) indexed=no        # Masked input
- tags (string, tag[autocomplete=10,separator=','])   # Tag input with autocomplete
```

### Pickers
```cnd
- image (weakreference, picker[type='image']) < jmix:image
- document (weakreference, picker[type='file']) < jnt:file
- folder (weakreference, picker[type='folder']) < jnt:folder
- linkedPage (weakreference, picker[type='page']) < jnt:page
- content (weakreference, picker[type='editorial']) < jnt:page, jmix:mainResource
- category (weakreference, picker[type='category']) < jnt:category
- assignedTo (weakreference, picker[type='user']) < jnt:user
- team (weakreference, picker[type='usergroup']) < jnt:group
- contentFolder (weakreference, picker[type='contentfolder']) < jnt:contentFolder
- site (weakreference, picker[type='site']) < jnt:virtualsite
```

### Date
```cnd
- eventDate (date, datepicker)
- publishAt (date, datetimepicker)
```

### Other
```cnd
- brandColor (string, color) = '#000000' mandatory autocreated nofulltext
- status (string, choicelist[resourceBundle]) = 'draft' mandatory < 'draft', 'published'
- country (string, choicelist[country])
- countryWithFlag (string, choicelist[country,flag])
- linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
```

---

## Keywords (always outside parentheses, after default, before constraints)

| Keyword | Meaning |
|---|---|
| `mandatory` | Field required — but does NOT guarantee non-null at render time |
| `i18n` | Internationalized (per locale) — must use `setPropertiesBatch` with `language:` |
| `multiple` | Allows multiple values |
| `autocreated` | Property created automatically with its default value |
| `protected` | Property cannot be modified by editors |
| `nofulltext` | Exclude from full-text search index |
| `indexed=no` | Don't index at all (use for passwords, internal IDs) |
| `facetable` | Enable for faceted search filtering |
| `hidden` | Hide from content editor UI |
| `orderable` | On node type: child nodes can be manually reordered |

**Order when combining:** `= default mandatory autocreated i18n`

```cnd
- color (string, color) = '#000000' mandatory autocreated nofulltext
- status (string) = 'open' autocreated
- hiddenCounter (long) = 10 hidden autocreated
- password (string, text[password]) indexed=no
- tags (string, tag[autocomplete=10,separator=',']) facetable nofulltext multiple
```

---

## Default Values

```cnd
- status (string) = 'draft'
- isVisible (boolean) = 'true'
- isFeatured (boolean) = 'false'
- publishDate (date) = now()
- priority (long) = '0'
- price (double) = '0.00'
- color (string, color) = '#000000' mandatory autocreated
- layout (string, choicelist[resourceBundle]) = 'left' mandatory < 'left', 'right', 'center'
```

**Multiple defaults (for multiple-value properties):**
```cnd
- sharedLong (long) = 1, 2 multiple
- sharedChoicelist (string, choicelist[resourceBundle]) = 'choice1', 'choice2' multiple < 'choice1', 'choice2', 'choice3'
```

**`resourceBundle('key')` — default from properties file:**

Use when the default value should vary by locale (e.g. richtext fields with pre-filled copy):

```cnd
- feedbackMsg (string, richtext) = resourceBundle('label.contactForm_feedbackMsg') autocreated mandatory i18n
```

Jahia reads the key from `settings/resources/<module>.properties` (or the locale-specific variant) when the node is first created and pre-fills the field. The corresponding properties entry:

```properties
label.contactForm_feedbackMsg=<i>Dear <b>$name</b></i> <br/> Thank you for reaching out!
```

> Note: `$name` here is a server-side template placeholder set by Jahia's forms engine — not the i18next `{{name}}` interpolation syntax used in `locales/*.json`.

---

## Constraints

Always come **last**, after keywords, using `<`:

### Choicelist values
```cnd
- status (string, choicelist[resourceBundle]) = 'draft' mandatory < 'draft', 'published', 'archived'
- priority (long, choicelist) < 20, 33, 50, 66, 80
- percentage (double, choicelist) < 20.0, 33.5, 50.0
```

### Reference type constraints
```cnd
- image (weakreference, picker[type='image']) mandatory < jmix:image
- linkedContent (weakreference) < jnt:page, jmix:mainResource
- page (weakreference) < jnt:page
```

### Regex constraints
```cnd
- email (string) < '^$|[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\\.)+[A-Za-z]{2,}'
- code (string) < '^[a-z0-9\\s]*$'
```

### Date range constraints (`(` `)` = exclusive, `[` `]` = inclusive)
```cnd
- startDate (date, datepicker) < '(2019-06-04T00:00:00.000,)'    # after date, exclusive
- endDate (date, datepicker) < '(,2021-06-20T00:00:00.000)'      # before date, exclusive
- eventDate (date, datepicker) < '[2019-06-04T00:00:00.000,]'    # on or after date
- rangeDate (date, datepicker) < '[2019-06-04T00:00:00.000,2021-06-20T00:00:00.000]'
```

---

## Node Type Structure

```cnd
<namespace = 'http://www.example.com/jahia/nt/1.0'>

[namespace:componentMixin] > jmix:droppableContent, jmix:accessControllableContent mixin

[namespace:newsArticle] > jnt:content, namespace:componentMixin
 - title (string) mandatory i18n
 - subtitle (string) i18n
 - publishDate (date) = now() mandatory
 - status (string, choicelist[resourceBundle]) = 'draft' mandatory < 'draft', 'published'
 - featuredImage (weakreference, picker[type='image']) mandatory < jmix:image
 - imageAlt (string) mandatory i18n
 - content (string, richtext) mandatory i18n
 - isFeatured (boolean) = 'false'
```

### Required elements
1. **Namespace declaration** — `<ns = 'http://...'>`
2. **Mixin** — must inherit from both `jmix:droppableContent` and `jmix:accessControllableContent`
3. **Component type** — inherits from `jnt:content` and your mixin

---

## Advanced Patterns

### Orderable child lists
```cnd
[ns:section] > jnt:content, ns:componentMixin orderable
 - - (ns:sectionItem)    # wildcard: any number of ns:sectionItem children, ordered
```

### Named children
```cnd
[ns:carousel] > jnt:content, ns:componentMixin
 - slides (ns:carouselSlides)    # exactly one named child of type ns:carouselSlides
```

### Dynamic mixins (field extends another type)
```cnd
[nsmix:featuredContent] > jmix:dynamicFieldset mixin
extends = ns:newsArticle
 - featuredLabel (string) i18n
```

### Dependent choicelist
```cnd
- country (string, choicelist[resourceBundle]) = 'france' < 'france', 'england'
- region (string, choicelist[regionChoiceListInitializer, dependentProperties='country'])
- city (string, choicelist[cityChoiceListInitializer, dependentProperties='country,region'])
```

### Category picker (node-based)
```cnd
- category (weakreference, choicelist[nodes='/sites/systemsite/categories;jnt:category',sort])
```

### Autocreated with hidden counter
```cnd
- viewCount (long) = 0 autocreated hidden
- status (string) = 'open' autocreated
```

---

## Common Mistakes

### ❌ Keywords inside parentheses
```cnd
- title (string, mandatory) i18n   # mandatory is NOT a selector
```
✅ `- title (string) mandatory i18n`

### ❌ Keywords before default value
```cnd
- status (string) mandatory = 'draft' < 'draft', 'published'
```
✅ `- status (string) = 'draft' mandatory < 'draft', 'published'`

### ❌ Constraints before keywords
```cnd
- image (weakreference) < jmix:image mandatory
```
✅ `- image (weakreference) mandatory < jmix:image`

### ❌ Missing comma between type and selector
```cnd
- content (string richtext)
```
✅ `- content (string, richtext)`

### ❌ Missing `<` before constraints
```cnd
- status (string, choicelist[resourceBundle]) 'draft', 'published'
```
✅ `- status (string, choicelist[resourceBundle]) < 'draft', 'published'`

### ❌ Defining taxonomy properties in CND
```cnd
- tags (string) multiple
- categories (weakreference) multiple
```
✅ Use `jmix:tagged` and `jmix:categorized` mixins + post-creation GraphQL. See `jahia-taxonomy-patterns.md`.

### ❌ Defining `j:url` or `j:linknode` directly
```cnd
- j:url (string)
- j:linknode (weakreference)
```
✅ Use the `linkTo` mixin with `linkTypeInitializer`. See `jahia-link-patterns.md`.

---

---

## UGC (User-Generated Content) written directly to LIVE workspace

Survey responses, votes, form submissions, and other anonymous UGC are written **directly to the LIVE workspace** via a system session — they never go through the default→live publication workflow. Two CND traps apply exclusively to this pattern.

### ❌ Using `jnt:contentList` as a UGC response container in LIVE

`jnt:contentList` carries `jmix:editorialContent` and versioning child semantics (`+ * (jnt:content) = jnt:contentList version`). Writing child nodes directly to a `jnt:contentList` in LIVE fails with `ConstraintViolationException` due to those versioning constraints. The error is silent in some configurations — the parent node is created but children are never stored.

```cnd
// ❌ WRONG — jnt:contentList rejects direct LIVE writes
[svy:survey] > jnt:content
  + responses (jnt:contentList) hidden

// ✅ CORRECT — custom lightweight container; no editorial mixins
[svy:responseList] > jnt:content, jmix:hiddenType
  orderable
  + * (svy:surveyResponse)

[svy:survey] > jnt:content
  + responses (svy:responseList) hidden
```

```java
// ✅ Correct
surveyNode.addNode("responses", "svy:responseList");

// ❌ Wrong
surveyNode.addNode("responses", "jnt:contentList");
```

**Rule**: any container written directly to LIVE must extend `jnt:content` + `jmix:hiddenType` only — no content-area mixins, no versioning semantics.

### ❌ Missing child node definition — addNode() silently rejected

Without an explicit child node definition, Jackrabbit rejects `addNode()` with `ConstraintViolationException`. Worse, the parent node save succeeds, leaving orphan nodes with no data and no visible error.

```cnd
// ❌ WRONG — svy:surveyResponse has no child definition; addNode("svy:questionResponse") throws
[svy:surveyResponse] > jnt:content, jmix:hiddenType
  - email (string)

// ✅ CORRECT — declare every level of the child chain explicitly
[svy:surveyResponse] > jnt:content, jmix:hiddenType
  orderable
  - email (string)
  + * (svy:questionResponse)           // ← required

[svy:questionResponse] > jnt:content, jmix:hiddenType
  - questionPath (string)
  - chosenOptions (string) multiple
```

**Rule**: every CND type that stores child nodes must declare `+ * (childType)`. Follow the chain top-down: `responseList → surveyResponse → questionResponse`.

---

## Validation Checklist

- [ ] Namespace declared at top
- [ ] Mixin inherits from `jmix:droppableContent` + `jmix:accessControllableContent`
- [ ] Component inherits from `jnt:content` and your mixin
- [ ] Type + selector in parentheses, comma-separated
- [ ] Default value before keywords
- [ ] Keywords outside parentheses
- [ ] Constraints last with `<`
- [ ] Image references constrain to `< jmix:image`
- [ ] No `j:tagList`, `j:defaultCategory`, `j:url`, or `j:linknode` declared directly
- [ ] All user-facing text properties have `i18n` keyword
- [ ] UGC containers in LIVE extend `jnt:content + jmix:hiddenType` only (not `jnt:contentList`)
- [ ] Every type that stores child nodes declares `+ * (childType)` explicitly
