---
paths:
  - "**/graphql/**"
  - "**/*.graphql"
  - "**/*.gql"
  - "**/useGQLQuery*"
  - "**/useJCRQuery*"
---

# GraphQL Rules

Auto-loaded when touching GraphQL files or query hooks. Full reference: `.agents/context/jahia-frontend-backend-patterns.md`.

## Endpoint & Auth

- Endpoint: `POST http://localhost:8080/modules/graphql`
- Always set `Origin` header — Jahia rejects requests without it.
- Auth: session-based (cookie). Never hardcode credentials.
- For i18n content: pass `language:` parameter in mutations.

## Query Design

- Reuse `GQLJCRNode` — do not define parallel response shapes.
- Compose from existing types via `... on GQLJCRNode { }` fragments.
- Authorize at the top of the resolver, once — never per-field.
- Avoid N+1: use `nodes(where: ...)` instead of looping over individual node fetches.

## Front-End Hooks (JS modules)

```tsx
// Server-side query (preferred for static data)
const { data } = useJCRQuery(gql`
  query { jcr { nodeByPath(path: "...") { ... } } }
`);

// Client-side (Islands only — needs 'use client')
const { data, loading } = useGQLQuery(QUERY, { variables: { ... } });
```

- Prefer `useJCRQuery` (server-side, zero client JS) over `useGQLQuery` (client-side, ships JS bundle).
- Always handle `loading` and `error` states in client components.

## GraphQL Extensions (OSGi modules)

- Annotate with `@GraphQLName`, `@GraphQLDescription` on every public type/field/mutation.
- Return `GQLJCRNode` where possible — avoids inventing parallel object graphs.
- Register via `GqlJcrNodeExtension` or `GqlJcrMutationExtension` OSGi component.

## Introspection

To fetch the live schema: `WebFetch http://localhost:8080/modules/graphql` with `{"query": "{ __schema { types { name } } }"}`.
