---
paths:
  - "**/*.tsx"
  - "**/*.ts"
  - "**/*.module.css"
  - "**/package.json"
  - "**/vite.config.*"
  - "**/webpack.config.*"
---

# Frontend Rules (JS Template Set & OSGi UI Extension)

Auto-loaded when touching TypeScript/React files. Full reference: `.agents/context/jahia-js-reference-patterns.md` and `.agents/context/jahia-frontend-backend-patterns.md`.

## React Version Enforcement — Non-Negotiable

| Context | React version | Bundler |
|---|---|---|
| JS template set (public site) | **React 19** | Vite |
| OSGi UI extension (jContent back-office) | **React 18** | Webpack + Module Federation |

**Never mix these.** Importing React 19 APIs in a back-office extension, or React 18 patterns in a template set, will cause runtime failures.

## JS Template Set (React 19 / Vite)

### Component Registration

```tsx
import { jahiaComponent } from '@jahia/javascript-modules-library';

jahiaComponent({
  componentType: 'view',          // or 'template'
  nodeType: 'namespace:MyType',
  name: 'default',                // matches CND view name
  displayName: 'My Component',
  component: MyComponent,
});
```

### Server Context (always server unless Island)

```tsx
import { useServerContext } from '@jahia/javascript-modules-library';

const MyComponent = () => {
  const { currentNode, renderContext } = useServerContext();
  // currentNode.properties.<field>.value
};
```

### Islands (client-side interactivity)

- Add `'use client';` directive at the top.
- Keep Islands small — only interactive parts. Everything else stays server.
- Use `useGQLQuery` only inside Islands.

### CSS Modules

- File: `component.module.css` co-located with the view.
- Import: `import styles from './component.module.css';`
- CSS variables always with fallback: `var(--color-primary, #1a1a1a)`.
- Theme scoping via wrapper class: `.myModule { ... }`.
- Never use global selectors inside CSS Modules.

### Build & Deploy

```bash
yarn build && yarn jahia-deploy   # always this sequence, never yarn dev from agent
```

## OSGi UI Extension (React 18 / Webpack / Module Federation)

- Register extensions via `registry.add(...)` from `@jahia/ui-extender`.
- Actions registered with `registry.add('action', ...)` — need `targets: ['jcontent-*']`.
- Dialogs via `registry.add('dialog', ...)` — must handle CSRF: include `jcrSessionInfo.token`.
- TCCL (Thread Context ClassLoader) issue: never load resources via `Thread.currentThread().getContextClassLoader()` in OSGi bundles with Module Federation.

## Performance

- Use `buildNodeUrl` for all node URL construction — never string-concat `/sites/` paths.
- Use `ModuleCacheProvider` for node rendering cache invalidation.
- `RenderChildren` / `RenderChild` for composing sub-components — avoids manual recursion.
- Responsive images: use `imageNodeToImgProps` utility from `@jahia/javascript-modules-library`.
