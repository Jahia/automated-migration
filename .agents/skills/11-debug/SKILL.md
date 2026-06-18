---
name: 11-debug
description: Debug build errors, deploy failures, runtime rendering issues, CND parse errors, and GraphQL errors on a running Jahia instance.
type: technical
phase: 11
status: active
allowed-tools: Bash, Read, WebFetch, Glob, Grep
---

# Skill: jahia-dev-debug

Diagnoses why a Jahia JavaScript module fails to load. Follows the deployment pipeline from source to runtime.

---

## Agent identity
- **Agent name:** Diagnost
- **Reference style:** Medicine / diagnostics
- **Signature line (en):** *"Symptoms lie. Logs tell the truth."*
- **Personality note:** Starts with logs, not hypotheses. Isolates one variable at a time. Documents the root cause, not just the fix.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## Load migration environment

```bash
ENV_FILE=$(find . -name "migration.env" | head -1)
if [ -z "$ENV_FILE" ]; then
  echo "ERROR: migration.env not found. Run /0-migration-start first."
  exit 1
fi
source "$ENV_FILE"
echo "Jahia: $JAHIA_URL | Site: $JAHIA_SITE_KEY | MCP: $MCP_AVAILABLE"
```

---

## Step 1 — Build

From the module directory (where `package.json` is):

```bash
yarn build
```

- **Build fails** → fix the TypeScript / bundling error shown and stop here. Do not proceed to deploy until the build is clean.
- **Build succeeds** → proceed to Step 2.

---

## Step 2 — Deploy

```bash
yarn jahia-deploy
```

Interpret the output:
- `"Operation successful"` in the response → deployment was accepted. Proceed to Step 3 — the module may still fail at runtime.
- `"{}"` or empty JSON → deployment was **rejected** (usually a CND parse error or missing dependency). Proceed to Step 3 to find the cause in the logs.
- Any other error → fix the connection issue (is Docker running?) then retry.

---

## Step 3 — Watch live Docker logs

> Do NOT analyse logs that already exist — an old error is not necessarily the cause of the current issue. Start a fresh log stream, then deploy again to capture only what happens as a result of this deployment.

### 3a — Start watching logs in the background

Find the Jahia container name:

```bash
docker ps --format '{{.Names}}' | grep -i jahia | head -1
```

Then start tailing:

```bash
docker logs -f <container-name> 2>&1 | grep -v "^\s*$" &
LOG_PID=$!
```

### 3b — Deploy again while logs are streaming

```bash
yarn jahia-deploy
```

### 3c — Wait ~15 seconds, then stop the log stream

```bash
sleep 15 && kill $LOG_PID 2>/dev/null
```

### 3d — Verify component registration

```bash
docker logs <container-name> 2>&1 | grep "Registered Jahia component"
```

Expected: one line per view registered, e.g.:
```
Registered Jahia component: mymodule_view_ns:hero_default
Registered Jahia component: mymodule_view_ns:hero_small
```

If a component you just deployed is **absent** from this list, its `jahiaComponent` call was never reached — usually a syntax/import error in the view file that prevented the module from fully loading.

---

## Step 4 — Find the first error

Scan the captured log output for the **first** error that appears **after** the deploy timestamp. Common patterns to look for:

| Pattern | Likely cause |
|---|---|
| `CND parse error` / `invalid node type` | CND syntax error or illegal field declaration |
| `NoSuchNodeTypeException` | A referenced type doesn't exist (wrong namespace, typo, missing dependency) |
| `ClassNotFoundException` / `NoClassDefFoundError` | Java dependency missing |
| `Cannot set property` / `TypeError` in JS stack | View runtime error |
| `Module ... failed to start` | Any of the above |
| `Unresolved requirement` | OSGi dependency not satisfied |
| Missing `Registered Jahia component` for a specific type | View file has a syntax/import error, or `jahiaComponent` not reached |

**Focus on the first error, not the last.** Later errors are often cascading failures caused by the first one.

---

## Step 5 — Fix and retry

Once the root cause is identified:

1. Fix the issue in the source files
2. Run `yarn build` again
3. Go back to Step 2

Repeat until `yarn jahia-deploy` succeeds and the module loads cleanly (no errors in the 15-second window after deploy).

---

## Common fixes by error type

### CND: `j:linknode` or `j:url` declared explicitly
These fields are injected by Jahia's `linkTypeInitializer` mixin. Remove them from the CND.

### CND: unknown mixin or type
Check that the namespace is declared at the top of `settings/definitions.cnd` and that all referenced types exist.

### import.xml: reference to a non-existent type
Any `jcr:primaryType` or `jcr:mixinTypes` value in `import.xml` must exist in the deployed CND. Check for typos.

### import.xml: `jmix:nolive` used as `jcr:primaryType`
`jmix:nolive` is a mixin — it goes in `jcr:mixinTypes`, not `jcr:primaryType`.

### import.xml: OSGi fails with `missing requirement … (nodetypes=jmix:nolive)`
Every `jcr:mixinTypes` value in `import.xml` is scanned by the OSGi bundle resolver. If the mixin is not declared in the module's own CND and is not provided by a resolvable dependency, the bundle will not start. Correct spelling is `jmix:nolive` (all lowercase). Verify the mixin exists in your Jahia instance before using it in `import.xml`.

### View: module loads but page is blank
Run `yarn dev` and check the Vite / SSR console for a React render error.

---

## Visual layout — section width and collapse

### Component renders but is full-width when it should be constrained

**Symptom:** A component's inner content spans the full viewport (e.g. 2560px) instead of the expected `max-width: 1140px`.

**Cause - `container` + `col-*` on same element:** Bootstrap `col-*` classes set `max-width: 100%` which overrides `container`'s `max-width: 1140px`. Even `col-12` wins over `container` on the same element.

**Diagnosis:**
```javascript
// In browser console:
const el = document.querySelector('.your-section .component-content');
getComputedStyle(el).maxWidth; // will show "100%" not "1140px"
```

**Fix:** Remove the `container` class and use an inline style instead:
```tsx
<div className="component-content" style={{ maxWidth: "1140px", margin: "0 auto", width: "100%" }}>
```

### Component collapses to ~50px height

**Common causes:**
1. **JS carousel with `overflow: hidden`** - Swiffy Slider and similar set this via JS. Without initialization, the container has height 0. Fix: replace with flex layout in SSR.
2. **`position: absolute` children inside non-positioned parent** - the parent has no height because absolute children are out of flow. Fix: add `position: relative; min-height: Xpx` to the parent, or change children to `position: static`.
3. **Empty content** - component renders nothing because JCR content is missing. Always check `document.querySelector('.component').innerHTML` before diagnosing CSS.

---

## GraalJS (server-side JS) debugging with Chrome DevTools

Use this when you need to step through server-side view code running inside GraalVM.

### Step 1 — Enable the inspector via GraphQL

In Jahia's Developer Tools > GraphQL editor, run:

```graphql
mutation {
  admin {
    jahia {
      configuration(pid: "org.jahia.modules.javascript.modules.engine.jsengine.GraalVMEngine") {
        polyGlotInspect: value(name: "polyglot.inspect", value: "0.0.0.0:9229")
        polyGlotInspectSuspend: value(name: "polyglot.inspect.Suspend", value: "false")
        polyGlotInspectSecure: value(name: "polyglot.inspect.Secure", value: "false")
      }
    }
  }
}
```

### Step 2 — Map the port

If running in Docker, ensure port `9229` is mapped in `docker-compose.yml`:

```yaml
ports:
  - "9229:9229"
```

### Step 3 — Connect Chrome

After the mutation, Jahia logs a `devtools://...` URL. Open it in Chrome (use latest; Chrome 117-118 had known debugger bugs).

### Step 4 — Set a breakpoint and debug

In Chrome DevTools Sources tab, open `<module>/dist/main.js`, set a breakpoint, then reload the page. The server-side render pauses at the breakpoint. Full scope inspection, step-over, and continue are supported.

The config file `org.jahia.modules.javascript.modules.engine.jsengine.GraalVMEngine.cfg` accepts any `polyglot.*` key as an engine option — you can persist these settings there instead of using the GraphQL mutation.
