# Context — Jahia Platform (8.2) Cheat Sheet

A compact reference for AI agents that need to recall how Jahia 8.2 fits together. **Not** a substitute for the official documentation — link out when in doubt.

## Layered architecture

| Layer | Tech / API |
|---|---|
| Persistence | JCR 2.0 (`javax.jcr`) backed by Apache Jackrabbit |
| Domain services | `JahiaSitesService`, `JCRStoreService`, `JCRTemplate` |
| Module runtime | OSGi (Apache Karaf), Declarative Services |
| HTTP | Servlet API + Jahia render filters + GraphQL |
| UI | jContent (React), Page Builder |

## Key abstractions

- **Site (`jnt:virtualsite`)** — top-level scope of authored content. All content lives under `/sites/<siteKey>/`.
- **Page (`jnt:page`)** — a tree of components rendered by a template. Templates select which Areas appear on the page.
- **Template** — a JCR node referencing render scripts. JS modules use `jahiaComponent({ componentType: "template", nodeType: "jnt:page" })`.
- **Node type definition (CND)** — schema for content. Both JS and OSGi modules ship CND files.
- **Area / AbsoluteArea** — editorial drop zones on a page. Areas are per-page; AbsoluteAreas are shared across pages (e.g. footer, navbar).
- **Content folder (`jnt:contentFolder`)** — stores `jmix:mainResource` content (articles, posts) that needs its own URL.
- **Workspace** — `default` for editing, `live` after publication. Always publish after JCR mutations.
- **Locale** — content is multi-lingual via translation nodes. i18n properties need `language:` in GraphQL mutations.

## Sessions (Java / OSGi)

- `JCRSessionWrapper` is per-user, per-workspace, per-locale, **and not thread-safe**.
- Obtain via `JCRTemplate.getInstance().doExecuteWithUserSession(...)`. The callback owns the session lifetime.
- Save changes explicitly (`session.save()`); do not rely on auto-commit.
- Never hold a session reference across threads.

## OSGi modules

- A Jahia module is an OSGi bundle with the `Jahia-Module-Type` manifest header.
- Build with `maven-bundle-plugin`, parent `org.jahia.modules:jahia-modules:8.2.0.0`.
- Hot-deploy via Jahia's tools UI or by dropping the JAR in `<jahia>/digital-factory-data/modules`.

## Module types and React versions

| Module type | React | Build | Entry library |
|---|---|---|---|
| JS template set (public site) | **19** | Vite | `@jahia/javascript-modules-library` |
| OSGi UI extension (back-office) | **18** | Webpack + Module Federation | `@jahia/ui-extender` |
| OSGi Java bundle | — | Maven | — |

React version is non-negotiable. The jcontent host shares its React 18 singleton with UI extensions; the public renderer runs React 19 independently.

## JS template sets

- Scaffolded with `npx @jahia/create-module@latest`.
- Components register with `jahiaComponent()` from `@jahia/javascript-modules-library`.
- Deploy with `yarn build && yarn jahia-deploy`. Never use `yarn dev` from an agent.

## OSGi UI extensions

- Webpack + Module Federation via `@jahia/webpack-config`.
- Register at `jahiaApp-init:N` via `registry.add('callback', ...)` from `@jahia/ui-extender`.
- Maven `frontend-maven-plugin` runs `yarn build:production` during `mvn install`.
- Action endpoints: `POST /cms/render/default/{lang}{path}.{actionName}.do` — require CSRF Guard `.cfg`.

## GraphQL

- Provided by the `graphql-dxm-provider` module.
- Endpoint: `http://localhost:8080/modules/graphql`
- Always include `-H "Origin: http://localhost:8080"` in curl requests — omitting it returns `Permission denied`.
- i18n properties require `language:` in the `properties()` call; without it they return empty.

## Useful service entry points (Java)

```java
JCRTemplate.getInstance().doExecuteWithUserSession(...)   // primary JCR access
JahiaSitesService.getInstance().getSiteByKey(siteKey)     // resolve a site
JCRSessionFactory.getInstance().getCurrentUser()          // current Jahia user
NodeTypeRegistry.getInstance().getNodeType(name)          // node type metadata
```

## Where to look in a module

| Path | Purpose |
|---|---|
| `pom.xml` | Parent version, packaging, dependencies (OSGi modules) |
| `package.json` | Module name, scripts (JS modules) |
| `src/main/resources/META-INF/definitions.cnd` | Node type definitions (OSGi) |
| `settings/definitions.cnd` | Namespace + shared mixins (JS modules) |
| `src/main/import/repository.xml` | Initial JCR content (OSGi) |
| `settings/import.xml` or `docker/provisioning.yml` | Initial JCR content (JS modules) |

## Further reading

- Jahia 8 documentation portal: https://academy.jahia.com
- Front-end developer tutorials: https://academy.jahia.com/tutorials-get-started/front-end-developer
- Native node types (CND source): https://github.com/Jahia/jahia/tree/master/war/src/main/webapp/WEB-INF/etc/repository/nodetypes
- Developer training: https://github.com/Jahia/developer-training/blob/main/js-training/slides.md
