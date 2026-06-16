---
name: jahia-dev-java
description: |
  Jahia 8.2 Java module development — creating OSGi modules, defining content types (CND),
  building JSP views, implementing backend logic (rules, actions, queries), and extending
  the Jahia UI (Content Editor, jContent, component registry).
  Trigger when the user is: creating or modifying a Java module, writing CND content type
  definitions, building JSP rendering views, implementing Jahia rules or actions, running
  JCR SQL2 queries, extending Content Editor or jContent UI, configuring OSGi services,
  or troubleshooting module deployment issues.
allowed-tools: Read
---

# Jahia 8.2 Java Developer Skill

---

## Jahia Action framework (canonical patterns)

Actions are the main back-end extension point used from JS modules. They are OSGi `@Component(service = Action.class)` beans exposed as HTTP endpoints.

### Endpoint URL pattern

```
POST /cms/render/{workspace}/{lang}/sites/{siteKey}.{actionName}.do
```

Always use **`live`** workspace in the URL — this is the workspace accessible to authenticated site visitors (OIDC/OKTA users). Using `default` restricts access to contributors and above.

```
POST /cms/render/live/fr/sites/mysite.addBookmark.do
```

The `lang` segment is required but only meaningful for content lookup; actions that work on paths can use any valid language.

### Minimal action skeleton

```java
@Component(service = Action.class, immediate = true)
public class MyAction extends Action {

    @Override
    public String getName() { return "myActionName"; }

    @Override
    public ActionResult doExecute(
            HttpServletRequest request, RenderContext renderContext,
            Resource resource, JCRSessionWrapper session,
            Map<String, List<String>> parameters, URLResolver urlResolver) throws Exception {

        // session is live workspace — read request params here
        String value = param(parameters, "paramName");
        // ... do work (see workspace pattern below) ...
        return jsonResponse(renderContext, HttpServletResponse.SC_OK,
            new JSONObject().put("status", "ok"));
    }

    static String param(Map<String, List<String>> params, String key) {
        List<String> vals = params.get(key);
        return (vals != null && !vals.isEmpty()) ? vals.get(0) : null;
    }

    static ActionResult jsonResponse(RenderContext ctx, int status, JSONObject body) throws Exception {
        HttpServletResponse resp = ctx.getResponse();
        resp.setStatus(status);
        resp.setContentType("application/json;charset=UTF-8");
        resp.getWriter().write(body.toString());
        resp.getWriter().flush();
        return ActionResult.OK;
    }
}
```

### Workspace pattern — which session to use

The live-workspace session passed to `doExecute` is read-only for content. Writes require a different session.

| Write target | Session to use | Pattern |
|---|---|---|
| User's own JCR node (bookmarks, prefs) | User session in **default** workspace | `JCRTemplate.getInstance().doExecuteWithUserSession(username, "default", null, cb)` |
| Content node (likes, reactions, counters) | **System** session in **default** workspace | `JCRTemplate.getInstance().doExecuteWithSystemSession(cb)` |

```java
// Pattern A — write to user's own node (user already has access)
final String username = session.getUserID();
JCRTemplate.getInstance().doExecuteWithUserSession(username, "default", null,
    defaultSession -> {
        JCRNodeWrapper userNode = defaultSession.getUserNode();
        // ... create/modify nodes under userNode ...
        defaultSession.save();
        return null;
    });

// Pattern B — write to a content node (user doesn't have write access)
// Capture results via single-element array (lambda can't write to non-final vars)
final boolean[] liked = {false};
final long[] count = {0L};
JCRTemplate.getInstance().doExecuteWithSystemSession((JCRSessionWrapper sysSession) -> {
    JCRNodeWrapper contentNode = sysSession.getNode(contentPath);
    // ... create/modify nodes under contentNode ...
    sysSession.save();
    liked[0] = true;
    count[0] = 42L;
    return null;
});
// Build JSONObject outside the lambda (avoids JSONException in JCRCallback)
return jsonResponse(renderContext, SC_OK,
    new JSONObject().put("liked", liked[0]).put("count", count[0]));
```

> ⚠️ Build `JSONObject` **outside** the lambda. `JCRCallback.doInJCR` only declares `throws RepositoryException`; if `JSONException` is checked in your version of `org.json`, the lambda won't compile. Use single-element arrays to pass results out.

### CSRF guard — required for every action

Every `POST` to an action endpoint is rejected by Jahia's CSRF guard unless the action name is whitelisted. Create a config file:

```
src/main/resources/META-INF/configurations/org.jahia.modules.jahiacsrfguard-<module>.cfg
```

```properties
whitelist = *.myActionName.do, *.anotherAction.do
```

The wildcard `*.actionName.do` matches the endpoint regardless of site key or language segment.

### Maven + Java version

The project must be compiled with **Java 17**. Homebrew's default `java` may be Java 21+ and will fail with opaque errors (`Range [0, 3) out of bounds for length 2`, `TypeTag :: UNKNOWN`).

```bash
JAVA_HOME=/opt/homebrew/Cellar/openjdk@17/17.0.16/libexec/openjdk.jdk/Contents/Home \
  mvn clean package -q -Denforcer.skip=true
```

Deploy the resulting JAR:

```bash
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -F "bundle=@target/mymodule-1.0.0-SNAPSHOT.jar" \
  "http://localhost:8080/modules/api/bundles"
```

### Client-side call (JS Island)

```ts
const actionBase = (siteKey: string) => `/cms/render/live/fr/sites/${siteKey}`;

const resp = await fetch(`${actionBase(siteKey)}.myActionName.do`, {
  method: "POST",
  credentials: "include",   // required: sends session cookie
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ param1: "value" }),
});
const data = await resp.json();
```

---

## When to load which reference

| Task | Reference file |
|------|---------------|
| Creating a new module, Maven pom.xml, deployment, Java 11/17, static assets, deploy-free coding, troubleshooting bundle errors | `references/modules.md` |
| Writing CND definitions, content type hierarchy, property types, choicelist initializers, modifying existing definitions | `references/content-types.md` |
| JSP views, view selection, `@cache` tag, caching configuration, navigation menus, rendering filters, AMP | `references/rendering.md` |
| Drools rules (DRL), JCR event listeners, JCR SQL2 queries, external data provider, permissions and roles | `references/backend.md` |
| OSGi bundle lifecycle, Declarative Services, Blueprint XML, package Import/Export, service registry, Karaf tooling | `references/osgi.md` |
| Content Editor JSON overrides, jContent UI extension points, component registry, custom selectors, settings pages, CKEditor | `references/ui-extensions.md` |

## Key Concepts Glossary

**Bundle / Module**
An OSGi JAR deployed into Jahia. Every Jahia module is an OSGi bundle. Jahia adds custom MANIFEST attributes (`Jahia-Module-Type`, `Jahia-Depends`, `Jahia-Root-Folder`) on top of standard OSGi headers.

**CND (Compact Namespace and Node Type Definition)**
Apache Jackrabbit standard file format (`definitions.cnd`) that declares content types. Lives at `src/main/resources/META-INF/definitions.cnd`.

**JCR (Java Content Repository)**
The underlying storage model. Content is a tree of nodes, each with a primary type and optional mixin types. Jahia uses Apache Jackrabbit Oak as the JCR implementation.

**jnt: prefix**
Jahia Node Types namespace (`http://www.jahia.org/jahia/nt/1.0`). Used for concrete content types like `jnt:content`, `jnt:page`, `jnt:file`.

**jmix: prefix**
Jahia Mixin namespace (`http://www.jahia.org/jahia/mix/1.0`). Used for abstract mixin types like `jmix:editorialContent`, `jmix:list`, `jmix:cache`.

**jmix:editorialContent**
Key mixin — makes a content type visible in jContent and enables content versioning. Required for any user-editable content type.

**jmix:droppableContent**
Base mixin for component categories. Types that inherit from this mixin create a component folder in the content picker sidebar.

**Declarative Services (DS)**
Preferred OSGi service mechanism in Jahia 8.2. Uses `@Component`, `@Activate`, `@Reference` annotations. Blueprint XML is deprecated as of Jahia 8.2.

**jahia-depends**
MANIFEST / pom.xml property declaring other module artifact IDs that this module requires. OSGi resolves dependencies before starting the bundle. Supports version ranges and optional dependencies.

**Embed-Dependency**
Felix Maven Bundle Plugin instruction to embed non-OSGi JARs inside the module JAR. Default scope: `compile|runtime`. Dependencies scoped `provided` are NOT embedded.

**Deploy-free coding**
Development workflow where source file changes (JSP, CSS, JS, CND) are picked up live without redeployment. Requires initial deploy and `Jahia-Source-Folders` MANIFEST attribute pointing to the project base directory.

**jahia:deploy Maven goal**
Deploys the compiled module JAR to a local Jahia server or Docker container. Usage: `mvn clean install jahia:deploy -P <profile>`.

**Content Editor**
Jahia's React-based form UI for creating/editing content. Forms are generated from CND definitions merged with JSON override files. Override files live in `META-INF/jahia-content-editor-forms/`.

**jContent**
Jahia's React-based content management UI. Extended via the component registry (`window.jahia.uiExtender.registry`). Used by editors to browse, create, and manage content.

**Component Registry**
JavaScript hashmap (`type + key → value`) used to inject UI elements (actions, accordions, nav items, selector types) into jContent and Content Editor at runtime. Access via `import {registry} from '@jahia/ui-extender'`.

**DRL (Drools Rule Language)**
Rule files placed at `META-INF/rules.drl` (all workspaces), `META-INF/default-rules.drl` (edit workspace only), or `META-INF/live-rules.drl` (live workspace only). Jahia provides a built-in DSL that simplifies rule conditions and consequences.

**Workspace**
Jahia has two JCR workspaces: `default` (edit/preview, where authors work) and `live` (what visitors see). Publication copies nodes from default to live.

**Felix Web Console**
OSGi administration UI at `http://localhost:8080/tools`. Shows bundle states, packages, services. Useful for diagnosing dependency issues.

**Karaf SSH Shell**
Command-line OSGi console accessible via `ssh -p 8101 jahia@localhost`. Key commands: `jahia:modules`, `bundle:requirements`, `jcr:query`.

**JCR SQL2**
Query language for the JCR. Syntax: `SELECT * FROM [nodetype] AS alias WHERE condition`. Use `ISDESCENDANTNODE(alias, '/path')` to scope queries. Do NOT query `nt:base` — use `jmix:searchable` instead for broad content queries.

**choicelist initializer**
Java class implementing `ModuleChoiceListInitializer` that populates dropdown values in Content Editor. Registered as an OSGi `@Component` service. Referenced in CND with `choicelist[keyName]` syntax.

**Rendering filter**
OSGi service implementing `RenderFilter`. Wraps every JSP/module render. Priority < 16 runs per-request; priority > 16 runs only on cache miss. Extend `AbstractFilter` to use condition setters.

**Migration scripts**
Groovy scripts in `src/main/resources/META-INF/patches/` that run once on module deployment to migrate JCR content or configuration.

**Module types**
`Jahia-Module-Type` MANIFEST value controls module behavior:
- `module` — regular content module (default)
- `system` — loaded early, provides system-level services
- `templatesSet` — template set module that defines site templates

**Static resources**
JS/CSS/images declared in `Jahia-Static-Resources` MANIFEST header (e.g. `/css,/icons,/javascript`). Served directly from the OSGi bundle JAR under `src/main/resources/`.
