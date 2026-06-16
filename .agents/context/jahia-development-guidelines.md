# Context — Jahia Development Guidelines (CTO Review Standards)

Generic architectural guidelines derived from CTO code reviews. Apply to every new Jahia module regardless of type. These are not style preferences — they are the criteria used at merge time.

---

## 1. GraphQL API design — design for GraphQL, not for the transport you're replacing

The most common mistake when building a GraphQL API is porting an existing API (REST, Webflow, RPC) response shape 1:1 into GQL types. GraphQL and REST have fundamentally different philosophies:

- **REST**: the server decides what the client gets.
- **GraphQL**: the client decides what it needs.

### Rules

**Reuse existing GQL types.** `GQLJCRNode` already exists, is well-tested, and carries the full node graph. Do not create parallel "response objects" that duplicate what it provides (path, uuid, displayName, properties, children, etc.).

```java
// ❌ Wrong — duplicating what GQLJCRNode already provides
public class TagOperationResult {
    private String nodePath;
    private String nodeUuid;
    private String errorMessage;  // GQLJCRNode + GQL errors handle this
}

// ✅ Right — return GQLJCRNode; let the client select what it needs
@GraphQLField
public List<GQLJCRNode> getUpdatedNodes() { ... }
```

**Compose types from what already exists.** Extend `GQLJCRNode`, reuse pagination helpers from the platform, and follow the existing `@GraphQLTypeExtension` + `@GraphQLField` patterns in the codebase.

**Let optional leaf resolution do its job.** Don't pre-build response shapes with data the client may never request. Return the graph; let the client query only what it needs.

**Service injection is `@Inject @GraphQLOsgiService`.** The standard in the Jahia GQL codebase:

```java
@GraphQLTypeExtension(Query.class)
public class MyQueryExtension {
    @Inject @GraphQLOsgiService
    private MyService myService;
}
```

Never use `getInstance()` in a GQL type or service. OSGi has a service registry — use it.

**Authorize early, once.** If a GQL mutation type operates on a scoped resource (e.g. a site), perform the authorization check in the type's constructor. Every subsequent field resolver can then trust it has already been validated.

```java
// ❌ Wrong — authorization repeated per-operation (5 calls for 5 mutations in one request)
public GqlResult renameTag(...) {
    JCRNodeWrapper site = getAuthorizedSiteNode(siteKey, session);
    ...
}

// ✅ Right — authorize once in the constructor
public class GqlTagManagerMutation {
    private final JCRNodeWrapper siteNode;

    public GqlTagManagerMutation(String siteKey, JCRSessionWrapper session) throws RepositoryException {
        this.siteNode = session.getNode("/sites/" + siteKey);
        if (!this.siteNode.hasPermission("tagManager")) {
            throw new DataFetchingException("Permission denied");
        }
    }
    // all field resolvers trust siteNode is valid and authorized
}
```

---

## 2. Service design — reuse platform infrastructure, don't reinvent it

Before implementing any iteration, batching, caching, or pagination logic, check whether the platform already provides it:

- **Pagination**: use the platform's existing pagination helper (not manual `offset`/`limit` logic).
- **Batch tag operations**: `TaggingService.renameTagUnderPath(...)` and `deleteTagUnderPath(...)` already handle path-scoped iteration and per-node callbacks — implement `TagActionCallback<X>`, don't re-implement the loop.
- **Cache invalidation**: `ModuleCacheProvider.getInstance()` exists for this; resolve it locally where needed rather than threading it through parameter chains.
- **JCR sessions**: `JCRSessionFactory.getInstance().getCurrentUserSession(Constants.EDIT_WORKSPACE)` — inline this at the call site; wrapping a single line in its own method adds indirection with no abstraction value.

**Separation of concerns — strict boundary between service and API layers.**

Business logic (data retrieval, cache flushes, observation manager toggling, partial-failure semantics) belongs in service classes. The GraphQL layer owns: request orchestration, authorization, service delegation, result shaping. If business logic is accumulating in the GQL type, extract it into a proper service class.

```
GQL type (extension, query, mutation)
    ↓ delegates to
Service class (business logic, JCR operations, external calls)
    ↓ delegates to
Platform services (TaggingService, JCRTemplate, JahiaSitesService, ...)
```

**Don't thread singleton references through parameter chains.** If a method needs a singleton, resolve it locally:

```java
// ❌ Wrong — threading a singleton through 5 method calls
protected static void flushNodeCaches(ModuleCacheProvider cacheProvider, String path) { ... }

// ✅ Right — resolve locally where used
ModuleCacheProvider cacheProvider = ModuleCacheProvider.getInstance();
cacheProvider.invalidate(path, true);
cacheProvider.flushRegexpDependenciesOfPath(path, true);
```

---

## 3. Memory and performance — batch operations

Batch operations that touch many JCR nodes can silently exhaust heap. Design the API to avoid loading full node lists into RAM.

### The two-interaction pattern for batch results

**Interaction 1 — the mutation itself returns lightweight summary data only:**

```java
// ✅ Return counts + failed paths (strings), never full node instances
public class BatchMutationResult {
    private final int updatedCount;
    private final int failedCount;
    private final List<String> failedPaths;  // strings, not GQLJCRNode
    // Optional: paginate failures — return at most 10 by default
}
```

**Interaction 2 — on user request, query failed nodes by path:**

```graphql
# Client queries failure details only when the user asks
query FailedNodes($paths: [String!]!) {
    jcr {
        nodesByPath(paths: $paths) {
            displayName
            path
            property(name: "j:tagList") { values }
        }
    }
}
```

This pattern:
- Keeps the mutation response lightweight regardless of node count.
- Lets the UI show "X updated, Y failed — show details" without loading node objects.
- Lets pagination and limits apply naturally to the failure detail query.

### Limits on batch operations

Always enforce a maximum on batch operations:

```java
if (failedPaths.size() >= MAX_FAILURES) break;  // stop collecting, report partial
```

Return at most N failures by default. Add pagination or a "show more" mechanism for the rest. Document the limit in the Javadoc.

### Single-pass processing — avoid redundant iterations

```java
// ❌ Three passes: collect → sort → map
List<JCRNodeWrapper> nodes = new ArrayList<>();
while (iter.hasNext()) nodes.add((JCRNodeWrapper) iter.nextNode());  // pass 1
nodes.sort(Comparator.comparing(JCRNodeWrapper::getPath));            // pass 2
return nodes.stream().map(n -> toGql(n)).collect(toList());           // pass 3

// ✅ Single loop, sort GQL result once at the end
List<GQLJCRNode> result = new ArrayList<>();
while (iter.hasNext()) result.add(toGql((JCRNodeWrapper) iter.nextNode()));
result.sort(Comparator.comparing(n -> n.getNode().getPath()));
return result;
```

---

## 4. Package organization

Flat packages are a navigation tax. Split into sub-packages that reflect responsibilities from the start:

```
org.example.mymodule/
├── graphql/          # GQL type extensions, query/mutation types, GQL-facing DTOs
├── service/          # OSGi service interfaces + implementations
│   ├── spi/          # Public interfaces (exported)
│   └── internal/     # Implementations (not exported)
├── model/            # Domain DTOs / value objects
└── servlet/          # Servlet filters (if exposing a REST API layer)
```

Exported packages in `pom.xml` BND config:
```xml
<Export-Package>org.example.mymodule.graphql, org.example.mymodule.service.spi</Export-Package>
<!-- service.internal and model are NOT exported -->
```

---

## 5. Documentation — Javadoc on every public service method

Every public method on a service class must have Javadoc. This is not optional.

**Why it matters for AI-assisted development** (from CTO review):
> Agentic coding tools rely heavily on Javadoc and inline comments to ground their understanding of a codebase. Well-documented service contracts dramatically improve the quality of AI-generated code that interacts with these classes — call sites, tests, refactors, related modules. Undocumented public APIs become a quality ceiling for everyone working with the codebase, human or otherwise.

### Required Javadoc structure for service methods

```java
/**
 * Renames a tag across all content nodes under the given site in both workspaces.
 *
 * <p>Iterates over all nodes tagged with {@code currentTag} under the site root,
 * renaming the tag value in both the {@code default} and {@code live} workspaces.
 * The JCR observation manager is disabled during the operation to suppress
 * intermediate events; it is restored in a {@code finally} block.</p>
 *
 * <p>On partial failure, the operation continues past individual node errors
 * and collects failures. The caller receives a result with both the success count
 * and the paths of failed nodes (up to {@link #MAX_FAILURES}).</p>
 *
 * @param siteKey    the site identifier; must be a valid, existing site key
 * @param currentTag the tag name to rename; must not be null or blank
 * @param newTag     the replacement tag name; must not be null or blank;
 *                   must not already exist under the same site
 * @param session    the authenticated user's JCR session; must have {@code tagManager}
 *                   permission on the site node (enforced at construction time)
 * @return a {@link BatchMutationResult} containing the count of updated nodes,
 *         the count of failures, and the paths of up to {@link #MAX_FAILURES}
 *         failed nodes; never null
 * @throws RepositoryException if the site node cannot be resolved or a workspace
 *                             session cannot be obtained
 */
public BatchMutationResult renameTag(String siteKey, String currentTag, String newTag,
        JCRSessionWrapper session) throws RepositoryException { ... }
```

**Class-level Javadoc** must describe:
- The service's role in the module.
- Threading expectations (is it a singleton? is it thread-safe?).
- How it relates to its platform-level dependencies (e.g. "GraphQL-facing orchestration layer over `TaggingService`; does not replace it").

**AI-assisted Javadoc generation:** Run an agent over new service classes with a detailed explanation of the context before asking it to generate documentation. Review and correct the output — this is faster than writing from scratch and produces better initial coverage.

---

## 6. Exception handling — be consistent across layers

Decide per layer what exceptions propagate and what gets converted:

| Layer | Behavior |
|---|---|
| **Repository / JCR layer** | Let `RepositoryException` propagate — it's the platform contract |
| **Service layer** | Catch infrastructure exceptions, wrap in domain exceptions where meaningful; let `RepositoryException` propagate to the GQL layer |
| **GQL layer** | Convert `RepositoryException` to `DataFetchingException`; never swallow |

Don't mix: a method should not both declare `throws RepositoryException` and silently convert some `RepositoryException`s to `DataFetchingException` mid-stream. Pick one and apply it consistently.

---

## 7. Testing — Cypress from the start

New functional surfaces must ship with Cypress coverage. Tests added retroactively tend to slip indefinitely.

Minimum coverage for any new GQL mutation or query:

```
cypress/integration/my-feature/
├── happy-path.spec.js     # each mutation/query with valid inputs
├── authorization.spec.js  # unauthorized user, wrong site, wrong workspace
└── edge-cases.spec.js     # empty results, partial failure, limits
```

Do not use the legacy Jahia test framework for new features.

---

## 8. Code quality — method design

**Don't wrap single-line calls in methods.** A method that exists only to delegate a one-liner adds indirection without abstraction:

```java
// ❌ No value — readers jump to definition to find nothing interesting
protected JCRSessionWrapper getCurrentUserEditSession() throws RepositoryException {
    return JCRSessionFactory.getInstance().getCurrentUserSession(Constants.EDIT_WORKSPACE);
}

// ✅ Inline it — the expression is already self-explanatory
JCRSessionWrapper session = JCRSessionFactory.getInstance()
    .getCurrentUserSession(Constants.EDIT_WORKSPACE);
```

Extract a method only when it:
- Encapsulates non-trivial logic.
- Is called from more than one place with meaningful intent at the call site.
- Has a name that communicates more than the expression it wraps.

---

## Quick reference — merge checklist

- [ ] GraphQL types reuse `GQLJCRNode` and platform types; no parallel response objects
- [ ] Service injection via `@Inject @GraphQLOsgiService`; no `getInstance()` in GQL types
- [ ] Authorization performed once (e.g. in mutation type constructor), not per-operation
- [ ] Platform batch APIs used (e.g. `TaggingService.renameTagUnderPath`) — not reimplemented
- [ ] Batch results return counts + paths (strings), not full node instances
- [ ] Batch operations enforce a maximum failure count
- [ ] Singleton references resolved locally; not threaded through parameter chains
- [ ] No single-line wrapper methods
- [ ] No multi-pass loops where a single pass suffices
- [ ] Exception handling consistent per layer
- [ ] Packages split by responsibility (graphql, service/spi, service/internal, model)
- [ ] Javadoc on every public service class and method (class role, threading, params, return, throws)
- [ ] Cypress tests covering happy path, authorization failure, and edge cases
