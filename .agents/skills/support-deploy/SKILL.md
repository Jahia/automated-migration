---
name: support-deploy
description: Build and deploy a Jahia JS module to a local Jahia instance. Use after implementing components or making changes, to push the module and verify it loads correctly.
allowed-tools: Bash, Read
---

# Skill: Deploy Module

Compiles and deploys the Jahia JS module to the local Jahia instance.

---

## Build and deploy

From inside the module directory:

```bash
yarn build && yarn jahia-deploy
```

- `yarn build` — Vite compiles TypeScript, CSS Modules, and client bundles. Output: `dist/`
- `yarn jahia-deploy` — packages the dist as a `.tgz` and uploads it to Jahia at `http://localhost:8080`

**Never use `yarn dev` from an agent** — it is an interactive file watcher for humans only.

---

## Verify registration

After deploy, confirm components registered:

```bash
docker logs $(docker ps --format '{{.Names}}' | grep -i jahia | head -1) 2>&1 \
  | grep "Registered Jahia component" | tail -20
```

Expected: one line per view registered (e.g. `ns:heroSection`, `ns:jcrQuery`).

If a component is missing from the log, check for TypeScript errors in the build output.

---

## Verify types deployed

```bash
curl -s -u root:root \
  "http://localhost:8080/modules/tools/definitionsBrowser.jsp" \
  | grep "ns:"
```

Or use the browser: http://localhost:8080/modules/tools/definitionsBrowser.jsp

---

## Common build failures

| Error | Cause | Fix |
|---|---|---|
| `Cannot find module './types.js'` | Wrong import extension | Change `./types.ts` to `./types.js` |
| `Property 'X' does not exist on type 'Props'` | Missing field in types.ts | Add `X?: <type>` to Props interface |
| `JSX element type 'X' does not have any construct` | Missing import | Add `import X from "./X.client.jsx"` |
| `No child node definition found` | Mixin missing `+ childName` | Add child slot to mixin in definitions.cnd |
| `No rendering set for node` | Component not deployed | Re-run `yarn build && yarn jahia-deploy` |

---

## Hot-fix without full redeploy

For a CSS-only or minor TSX change:

```bash
yarn build && yarn jahia-deploy
```

There is no partial deploy — the full tgz is always uploaded. Build time is typically 5-15 seconds.

---

## Validation checklist
- [ ] `yarn build` exits 0 (no TypeScript or Vite errors)
- [ ] `yarn jahia-deploy` uploads successfully (no 4xx/5xx)
- [ ] Docker logs show `Registered Jahia component` for each new type
- [ ] New content types appear in Jahia content editor picker
- [ ] Existing pages still render (no regressions)
