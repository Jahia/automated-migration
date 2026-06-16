# Context — Jahia GraphQL Schema Reference

Auto-generated from a live Jahia 8.2 instance via introspection (323 types total, 310 custom).  
This file covers the types agents use most. For the full schema, run an introspection query against the running instance.

---

## Top-level Entry Points

### Query

```graphql
query {
  jcr(workspace: EDIT | LIVE): JCRQuery!         # All JCR read operations
  admin: AdminQuery!                              # Admin operations
  currentUser: Current_32_user                   # Authenticated user info
  search(...): augmentedSearchResult             # Full-text / Elasticsearch search
  jcontent: GqlJContent                          # jcontent-specific queries
  tag: JCRTags                                   # Tag management
  workflow: WorkflowService                      # Workflow queries
  forms: GqlEditorForms                          # Content editor forms
  dashboard: GqlDashboard                        # Dashboard
  contentBulkEdit: ContentBulkEditOperations     # Bulk editing
}
```

### Mutation

```graphql
mutation {
  jcr(workspace: EDIT | LIVE, save: Boolean = true): JCRMutation  # All JCR write operations
  admin: AdminMutation!
  jcontent: GqlJContentMutations
  survey: SurveyMutations                        # Custom extension (survey-service module)
  jwtToken(scopes: [String]!, ...): JWTToken
  contentBulkEdit: ContentBulkEditOperations
}
```

> **Critical**: `jcr()` defaults to `workspace: EDIT`. Anonymous users need `jcr(workspace: LIVE)` — DEFAULT workspace returns `PathNotFoundException` for unauthenticated sessions.

---

## JCRQuery — Read Operations

```graphql
type JCRQuery {
  # Fetch a single node
  nodeByPath(path: String!, validInLanguage: String): JCRNode
  nodeById(uuid: String!, validInLanguage: String): JCRNode

  # Fetch multiple nodes
  nodesByPath(paths: [String!]!, validInLanguage: String): [JCRNode]!
  nodesById(uuids: [String!]!, validInLanguage: String): [JCRNode]!

  # Paginated query with QOM
  nodesByCriteria(
    criteria: InputGqlJcrNodeCriteriaInput!
    before: String, after: String, first: Int, last: Int
    offset: Int, limit: Int
    fieldFilter: InputFieldFiltersInput
    fieldSorter: InputFieldSorterInput
    fieldGrouping: InputFieldGroupingInput
  ): JCRNodeConnection

  # Raw JCR-SQL2 / XPATH query
  nodesByQuery(
    query: String!
    queryLanguage: QueryLanguage = SQL2
    language: String
    before: String, after: String, first: Int, last: Int
    offset: Int, limit: Int
    fieldFilter: InputFieldFiltersInput
    fieldSorter: InputFieldSorterInput
  ): JCRNodeConnection

  # Node type introspection
  nodeTypeByName(name: String!): JCRNodeType
  nodeTypes(filter: InputNodeTypesListInput, ...): JCRNodeTypeConnection
  nodeTypesByNames(names: [String]!): [JCRNodeType]

  workspace: Workspace!
}
```

---

## JCRMutation — Write Operations

```graphql
type JCRMutation {
  # Create
  addNode(
    parentPathOrId: String!
    name: String!
    primaryNodeType: String!
    useAvailableNodeName: Boolean
    mixins: [String]
    properties: [InputJCRProperty]
    children: [InputJCRNode]
  ): JCRNodeMutation

  addNodesBatch(nodes: [InputJCRNodeWithParent]!): [JCRNodeMutation]

  # Read back mutated node
  mutateNode(pathOrId: String!): JCRNodeMutation
  mutateNodes(pathsOrIds: [String]!): [JCRNodeMutation]
  mutateNodesByQuery(query: String!, queryLanguage: QueryLanguage = SQL2, limit: Long, offset: Long): [JCRNodeMutation]

  # Move / Copy
  moveNode(pathOrId: String!, destParentPathOrId: String!, destName: String): JCRNodeMutation
  moveNodes(nodes: [InputCarriedJCRNode!]!): [JCRNodeMutation]
  copyNode(pathOrId: String!, destParentPathOrId: String!, destName: String, childNodeTypesToSkip: [String]): JCRNodeMutation

  # Delete
  deleteNode(pathOrId: String!): Boolean
  markNodeForDeletion(pathOrId: String!, comment: String): Boolean
  unmarkNodeForDeletion(pathOrId: String!): Boolean

  # Paste
  pasteNode(mode: PasteMode!, pathOrId: String!, destParentPathOrId: String!, destName: String, namingConflictResolution: NodeNamingConflictResolutionStrategy = FAIL): JCRNodeMutation

  modifiedNodes: [JCRNode]
  importContent(parentPathOrId: String!, file: String!, rootBehaviour: Int = 2): Boolean
}
```

### JCRNodeMutation — Per-node operations

```graphql
type JCRNodeMutation {
  # Node creation
  addChild(name: String!, primaryNodeType: String!, useAvailableNodeName: Boolean, mixins: [String], properties: [InputJCRProperty], children: [InputJCRNode]): JCRNodeMutation
  addChildrenBatch(nodes: [InputJCRNode]!): [JCRNodeMutation]

  # Properties
  setPropertiesBatch(properties: [InputJCRProperty]): [JCRPropertyMutation]
  mutateProperty(name: String!): JCRPropertyMutation
  mutateProperties(names: [String]): [JCRPropertyMutation]
  deletePropertiesBatch(properties: [InputJCRDeletedProperty]): Boolean

  # Mixins
  addMixins(mixins: [String]!): [String]
  removeMixins(mixins: [String]!): [String]

  # Move / Rename / Delete
  move(destPath: String, parentPathOrId: String, renameOnConflict: Boolean): String
  rename(name: String!): String
  delete: Boolean
  markForDeletion(comment: String): Boolean
  unmarkForDeletion: Boolean

  # Child navigation
  mutateChildren(names: [String], typesFilter: InputNodeTypesInput, propertiesFilter: InputNodePropertiesInput): [JCRNodeMutation]
  mutateDescendant(relPath: String!): JCRNodeMutation

  # Publication
  publish(languages: [String], publishSubNodes: Boolean = true, includeSubTree: Boolean = false): Boolean
  unpublish(languages: [String]): Boolean

  # Reorder
  reorderChildren(names: [String]!, position: ReorderedChildrenPosition = INPLACE): Boolean

  # Locking
  lock(type: String = "user"): Boolean
  unlock(type: String = "user"): Boolean
  clearAllLocks: Boolean

  # ACL
  grantRoles(roleNames: [String]!, principalType: PrincipalType!, principalName: String!): Boolean
  revokeRoles(roleNames: [String]!, principalType: PrincipalType!, principalName: String!): Boolean

  # Accessors
  node: JCRNode
  uuid: String
  createVersion: Boolean
}
```

### JCRPropertyMutation

```graphql
type JCRPropertyMutation {
  setValue(language: String, type: JCRPropertyType, option: JCRPropertyOption, value: String): Boolean
  setValues(language: String, type: JCRPropertyType, option: JCRPropertyOption, values: [String]): Boolean
  addValue(language: String, type: JCRPropertyType, option: JCRPropertyOption, value: String): Boolean
  addValues(language: String, type: JCRPropertyType, option: JCRPropertyOption, values: [String]): Boolean
  removeValue(language: String, type: JCRPropertyType, option: JCRPropertyOption, value: String): Boolean
  removeValues(language: String, type: JCRPropertyType, option: JCRPropertyOption, values: [String]): Boolean
  delete(language: String): Boolean
  path: String
  property: JCRProperty
}
```

---

## Core Node Types

### JCRNode (interface)

All node objects implement `JCRNode`. The concrete types are `GenericJCRNode`, `JCRSite`, etc.

```graphql
interface JCRNode {
  # Identity
  uuid: String!
  name: String!
  path: String!
  depth: Int!
  workspace: Workspace!

  # Display
  displayName(language: String): String
  url: String
  renderUrl(workspace: Workspace!, language: String!, findDisplayable: Boolean = false): String
  thumbnailUrl(name: String, checkIfExists: Boolean = false): String
  ajaxRenderUrl: String

  # Properties
  property(name: String!, language: String, useFallbackLanguage: Boolean = false): JCRProperty
  properties(names: [String], language: String, fieldFilter: InputFieldFiltersInput, useFallbackLanguage: Boolean = false): [JCRProperty]!

  # Navigation
  parent: JCRNode
  ancestors(upToPath: String, fieldFilter: InputFieldFiltersInput): [JCRNode]!
  children(
    names: [String], validInLanguage: String
    typesFilter: InputNodeTypesInput, propertiesFilter: InputNodePropertiesInput
    fieldFilter: InputFieldFiltersInput, fieldSorter: InputFieldSorterInput
    before: String, after: String, first: Int, last: Int, offset: Int, limit: Int
    includesSelf: Boolean = false
  ): JCRNodeConnection
  descendant(relPath: String!): JCRNode
  descendants(
    typesFilter: InputNodeTypesInput, validInLanguage: String
    propertiesFilter: InputNodePropertiesInput
    recursionTypesFilter: InputNodeTypesInput
    fieldFilter: InputFieldFiltersInput, maxDepth: Int
    before: String, after: String, first: Int, last: Int, offset: Int, limit: Int
  ): JCRNodeConnection

  # Cross-workspace
  nodeInWorkspace(workspace: Workspace!): JCRNode

  # References
  references(before: String, after: String, first: Int, last: Int, ...): JCRPropertyConnection!
  referenceCount(typesFilter: InputNodeTypesInput): Int
  usages(before: String, after: String, ...): UsageConnection!

  # Node type
  primaryNodeType: JCRNodeType!
  mixinTypes(fieldFilter: InputFieldFiltersInput): [JCRNodeType]!
  isNodeType(type: InputNodeTypesInput!): Boolean!
  allowedChildNodeTypes(includeSubTypes: Boolean = true, fieldFilter: InputFieldFiltersInput): [JCRNodeType]
  definition: JCRNodeDefinition

  # Site
  site: JCRSite

  # Rendering
  renderedContent(view: String, templateType: String, contextConfiguration: String, language: String, mainResourcePath: String, isEditMode: Boolean, requestAttributes: [InputRenderRequestAttributeInput]): RenderedNode
  isDisplayableNode: Boolean
  displayableNode: JCRNode

  # Publication
  aggregatedPublicationInfo(language: String!, subNodes: Boolean = false, references: Boolean = false): GqlPublicationInfo!

  # Permissions
  hasPermission(permissionName: String!): Boolean
  isExternal: Boolean!
  lockedAndCannotBeEdited: Boolean

  # Translation
  translationLanguages(isActiveOnly: Boolean): [String]
  languagesToTranslate(languagesTranslated: [String], languagesToCheck: [String]): [String]
  aggregatedLastModifiedDate(language: String, recursionTypesFilter: InputNodeTypesInput): String

  # Misc
  acl: GqlAcl
  vanityUrls(languages: [String], fieldFilter: InputFieldFiltersInput): [VanityUrl]
  lockInfo: LockInfo
  wipInfo: wipInfo
  defaultWipInfo: wipInfo
  findAvailableNodeName(nodeType: String, language: String): String
}
```

> **UUID vs path**: `path` reflects the access context — it differs when a node is accessed via `jnt:contentReference` (renders as `/sites/.../home/page/area/ref@/ref/node`). Use `uuid` as the stable cross-context identifier.

### JCRProperty

```graphql
type JCRProperty {
  name: String!
  path: String!
  type: JCRPropertyType!
  language: String
  internationalized: Boolean!
  node: JCRNode!

  # Single-value accessors
  value: String
  booleanValue: Boolean
  longValue: Long
  floatValue: Float
  notZonedDateValue: String   # Format: yyyy-MM-dd'T'HH:mm:ss.SSS
  decryptedValue: String

  # Multi-value accessors (for properties declared `multiple`)
  values: [String]
  booleanValues: [Boolean]
  longValues: [Long]
  floatValues: [Float]
  notZonedDateValues: [String]
  decryptedValues: [String]

  # Reference accessors
  refNode: JCRNode
  refNodes: [JCRNode]

  # Choicelist display
  choicelistValue(renderer: String, language: String): String
  choicelistValues(renderer: String, language: String): [String]

  # Rendered
  renderedValue: String
  renderedValues: [String]

  # Binary
  size: Long

  definition: JCRPropertyDefinition
}
```

> **`property()` vs `properties()`**: `property(name: "x")` returns a single `JCRProperty` — access `.value` or `.values` directly. `properties(names: ["x"])` returns `[JCRProperty]` — you must index the array first, e.g. `props[0].values`. Confusing these returns `undefined` in TypeScript.

### JCRSite

Extends `JCRNode` with site-specific fields:

```graphql
type JCRSite {
  # ... all JCRNode fields, plus:
  sitekey: String
  serverName: String
  defaultLanguage: String
  description: String
  languages: [JCRSiteLanguage]
  homePage: JCRNode
  installedModules: [String]
  installedModulesWithAllDependencies: [String]
}
```

---

## Pagination Types

```graphql
type JCRNodeConnection {
  nodes: [JCRNode]
  edges: [JCRNodeEdge]
  pageInfo: PageInfo!
  aggregation: JCRNodeAggregation
}

type JCRNodeEdge {
  node: JCRNode
  cursor: String!
  index: Int
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
  nodesCount: Int
  totalCount: Int
}

type JCRPropertyConnection {
  nodes: [JCRProperty]
  edges: [JCRPropertyEdge]
  pageInfo: PageInfo!
}
```

---

## Input Types

### Property / Node creation

```graphql
input InputJCRProperty {
  name: String!
  value: String
  values: [String]
  language: String          # required for i18n properties
  type: JCRPropertyType
  option: JCRPropertyOption
}

input InputJCRNode {
  name: String!
  primaryNodeType: String!
  useAvailableNodeName: Boolean
  mixins: [String]
  properties: [InputJCRProperty]
  children: [InputJCRNode]
}
```

### Criteria-based queries

```graphql
input InputGqlJcrNodeCriteriaInput {
  nodeType: String!          # e.g. "svy:question"
  paths: [String]            # restrict to these paths
  pathType: PathType         # ANCESTOR | PARENT | OWN
  language: String
  nodeConstraint: InputGqlJcrNodeConstraintInput
  ordering: InputGqlOrdering
}

input InputGqlJcrNodeConstraintInput {
  # Logical combiners
  all: [InputGqlJcrNodeConstraintInput]
  any: [InputGqlJcrNodeConstraintInput]
  none: [InputGqlJcrNodeConstraintInput]
  # Property matchers (set property: "propName" on same object)
  property: String
  equals: String
  notEquals: String
  contains: String
  like: String
  exists: Boolean
  gt: String
  gte: String
  lt: String
  lte: String
  lastDays: Int
  function: QueryFunction
}

input InputGqlOrdering {
  property: String
  orderType: OrderType       # ASC | DESC
}
```

### Type / property filters

```graphql
input InputNodeTypesInput {
  types: [String]!
  multi: MulticriteriaEvaluation    # ALL | ANY | NONE
}

input InputNodePropertiesInput {
  filters: [InputNodePropertyInput]!
  multi: MulticriteriaEvaluation
}

input InputNodePropertyInput {
  property: String!
  value: String
  language: String
  evaluation: PropertyEvaluation    # PRESENT | ABSENT | EQUAL | DIFFERENT
}

input InputFieldFiltersInput {
  filters: [InputFieldFilterInput]!
  multi: MulticriteriaEvaluation
}

input InputFieldFilterInput {
  fieldName: String
  value: String
  values: [String]
  evaluation: FieldEvaluation       # EQUAL | DIFFERENT | EMPTY | NOT_EMPTY | CONTAINS | CONTAINS_IGNORE_CASE | AMONG
  fieldFilter: InputFieldFiltersInput  # nested filter
}
```

---

## Enums

```graphql
enum Workspace { EDIT  LIVE }
enum QueryLanguage { SQL2  XPATH }
enum OrderDirection { ASC  DESC }
enum OrderType { ASC  DESC }
enum PathType { ANCESTOR  PARENT  OWN }
enum MulticriteriaEvaluation { ALL  ANY  NONE }
enum PropertyEvaluation { PRESENT  ABSENT  EQUAL  DIFFERENT }
enum FieldEvaluation { EQUAL  DIFFERENT  EMPTY  NOT_EMPTY  CONTAINS  CONTAINS_IGNORE_CASE  AMONG }

enum JCRPropertyType {
  STRING  BOOLEAN  DATE  LONG  DOUBLE  DECIMAL  BINARY
  NAME  PATH  REFERENCE  WEAKREFERENCE  URI  UNDEFINED
}

enum PublicationStatus {
  PUBLISHED  MODIFIED  NOT_PUBLISHED  UNPUBLISHED  DELETED  MARKED_FOR_DELETION
  MANDATORY_LANGUAGE_UNPUBLISHABLE  MANDATORY_LANGUAGE_VALID
  LIVE_MODIFIED  LIVE_ONLY  CONFLICT
}
```

---

## JCRNodeType

```graphql
type JCRNodeType {
  name: String
  displayName(language: String!): String
  icon: String
  mixin: Boolean
  abstract: Boolean
  queryable: Boolean
  hasOrderableChildNodes: Boolean
  systemId: String           # module name that declares this type
  properties(fieldFilter: InputFieldFiltersInput): [JCRPropertyDefinition]
  nodes(fieldFilter: InputFieldFiltersInput): [JCRNodeDefinition]
  supertypes(fieldFilter: InputFieldFiltersInput): [JCRNodeType]
  subTypes(before: String, after: String, first: Int, last: Int, offset: Int, limit: Int): JCRNodeTypeConnection
  extends(...): JCRNodeTypeConnection
  extendedBy(...): JCRNodeTypeConnection
  isNodeType(type: InputNodeTypesInput!): Boolean!
  primaryItem: JCRItemDefinition
}
```

---

## Custom Extension — survey-service

The `survey-service` OSGi bundle adds a `survey` field to the root `Mutation`.

```graphql
# Root Mutation entry point
mutation {
  survey: SurveyMutations
}

type SurveyMutations {
  submitResponse(
    surveyPath: String!
    email: String!
    answers: [InputSurveyAnswerInput]!
  ): SurveyResponsePayload
}

type SurveyResponsePayload {
  success: Boolean!
  code: String!            # "OK" | "DUPLICATE_EMAIL"
  responseId: String       # UUID of the created svy:surveyResponse node; null on failure
}

# graphql-java-annotations prepends "Input" to @GraphQLName — the schema name is InputSurveyAnswerInput
input InputSurveyAnswerInput {
  questionPath: String!    # UUID of the svy:question node
  optionId: String!        # UUID of the svy:questionOption node
}
```

**Calling the survey mutation** (anonymous, no auth needed):

```graphql
mutation SubmitSurveyResponse($surveyPath: String!, $email: String!, $answers: [InputSurveyAnswerInput]!) {
  survey {
    submitResponse(surveyPath: $surveyPath, email: $email, answers: $answers) {
      success
      code
      responseId
    }
  }
}
```

Required HTTP headers:
```
Content-Type: application/json
Origin: http://localhost:8080
X-Requested-With: XMLHttpRequest   # CSRF guard — required
```

---

## Common Query Patterns

### Fetch a node and its properties

```graphql
query {
  jcr(workspace: LIVE) {
    nodeByPath(path: "/sites/mySite/contents/my-article") {
      uuid
      name
      displayName(language: "en")
      property(name: "title", language: "en") { value }
      property(name: "publishDate") { value }
      primaryNodeType { name }
    }
  }
}
```

### Fetch children by type

```graphql
query {
  jcr {
    nodeByPath(path: "/sites/mySite/contents/survey") {
      children(typesFilter: { types: ["svy:question"] }) {
        nodes {
          uuid
          name
          displayName(language: "en")
        }
      }
    }
  }
}
```

### Paginated query with JCR-SQL2

```graphql
query {
  jcr(workspace: LIVE) {
    nodesByQuery(
      query: "SELECT * FROM [svy:surveyResponse] AS r WHERE ISDESCENDANTNODE(r, '/sites/mySite/contents/survey')"
      queryLanguage: SQL2
      limit: 100
    ) {
      nodes {
        uuid
        property(name: "email") { value }
        children(typesFilter: { types: ["svy:questionResponse"] }) {
          nodes {
            property(name: "chosenOptions") { values }
          }
        }
      }
      pageInfo { totalCount hasNextPage }
    }
  }
}
```

### Create a node with properties

```graphql
mutation {
  jcr(workspace: EDIT) {
    addNode(
      parentPathOrId: "/sites/mySite/contents"
      name: "my-article"
      primaryNodeType: "jnt:content"
      mixins: ["jmix:tagged"]
      properties: [
        { name: "title", value: "Hello", language: "en" }
        { name: "body",  value: "<p>Content</p>", language: "en" }
      ]
    ) {
      uuid
      node { path }
    }
  }
}
```

### Set properties on an existing node (batch, i18n)

```graphql
mutation {
  jcr {
    mutateNode(pathOrId: "/sites/mySite/contents/my-article") {
      setPropertiesBatch(properties: [
        { name: "title", value: "Bonjour", language: "fr" }
        { name: "status", value: "published" }
      ])
      publish(languages: ["en", "fr"])
    }
  }
}
```

### Anonymous read (LIVE workspace)

```graphql
# Always use jcr(workspace: LIVE) for unauthenticated calls
query {
  jcr(workspace: LIVE) {
    nodeByPath(path: "/sites/mySite/home") {
      uuid
      displayName(language: "en")
    }
  }
}
```

---

## Gotchas and Traps

| Trap | Symptom | Fix |
|---|---|---|
| Using `EDIT` workspace without auth | `PathNotFoundException` | Use `jcr(workspace: LIVE)` for anonymous queries |
| `properties(names: [...]) { values }` vs `property(name: ...) { values }` | `.values` is `undefined` in TypeScript | `properties()` returns an array — index it; use `property()` for single known names |
| `path` varies by access context | Votes don't match across render paths | Use `uuid` as the stable identifier; never match nodes by path string |
| `graphql-java-annotations` INPUT setters never called | Input fields are null despite correct client payload | Read `DataFetchingEnvironment.getArgument("fieldName")` as `List<Map<String,Object>>` |
| Input types get `Input` prefix in schema | `SurveyAnswerInput` in Java → `InputSurveyAnswerInput` in schema | Run introspection to verify the actual schema name before writing client mutations |
| `@GraphQLNonNull List<T>` maps to `[T]!` not `[T!]!` | Schema validation rejects `[T!]!` in client | Only the list is non-null; items are nullable unless separately annotated |
| Missing `X-Requested-With: XMLHttpRequest` | `IllegalStateException("XHR header required")` from server | survey-service CSRF guard requires this header on every mutation call |
| Missing `uuid` + `workspace` on a `GenericJCRNode` selection | Apollo logs `"Missing fields uuid,workspace while extracting key from GenericJCRNode"` and degrades to per-query caching | Add `uuid` and `workspace` to **every** node selection set, including aliased descendants (`descendant`, `children.nodes`, etc.) — Apollo uses these two fields as the composite cache key for all JCR node types |

---

## References

- Jahia GraphQL playground: http://localhost:8080/modules/graphql  
- JCR browser: http://localhost:8080/modules/tools/jcrBrowser.jsp  
- survey-service patterns: `/Users/stephane/Runtimes/0.Modules/survey/survey-service/.agents/context/survey-service-patterns.md`
- Frontend/backend patterns (includes graphql-java-annotations traps): `.agents/context/jahia-frontend-backend-patterns.md`
