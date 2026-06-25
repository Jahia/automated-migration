---
name: support-deploy
description: Build and deploy a Jahia JS module to a local Jahia instance. Use after implementing components or making changes, to push the module and verify it loads correctly.
type: technical
phase: support
status: active
allowed-tools: Bash, Read
---

# Skill: Deploy Module

Compiles and deploys the Jahia JS module to the local Jahia instance.

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

## Build and deploy

From inside the module directory:

```bash
yarn build && yarn jahia-deploy
```

- `yarn build` — Vite compiles TypeScript, CSS Modules, and client bundles. Output: `dist/`
- `yarn jahia-deploy` — packages the dist as a `.tgz` and uploads it to Jahia at `$JAHIA_URL`

**Never use `yarn dev` from an agent** — it is an interactive file watcher for humans only.

---

### Cache flush (mandatory after every deploy)

Jahia caches rendered HTML. Without flushing, the old broken render persists even after a correct fix is deployed. Always flush immediately after deploy:

```bash
curl -s -u "$JAHIA_USER:$JAHIA_PASS" \
  "$JAHIA_URL/cms/render/default/fr/sites/$JAHIA_SITE_KEY/home.flushCaches.do" \
  -o /dev/null -w "Cache flush: %{http_code}\n"
```

Expected: `200`. If `401`: credentials wrong. If `404`: Jahia URL wrong or site not found.

Then wait 3 seconds and verify the module is active:

```bash
sleep 3
curl -s -u "$JAHIA_USER:$JAHIA_PASS" \
  "$JAHIA_URL/modules/api/bundles" \
  | python3 -c "
import json, sys, os
bundles = json.load(sys.stdin)
name = os.environ.get('MODULE_NAME', '')
matches = [b for b in bundles if name and name in b.get('symbolicName','')]
for m in matches:
    print(m.get('symbolicName'), '-', m.get('state'))
" 2>/dev/null || echo "Module check skipped (set MODULE_NAME env var to verify)"
```

**Never skip the cache flush.** A cached stale render looks identical to a code bug and wastes debugging time.

---

### OSGi bundle activation check (mandatory after every OSGi jar deploy)

After deploying a `.jar` via `docker cp`, the cache flush is not enough — the bundle must reach `Active` state in Karaf. A bundle can fail silently with no visible error: wrong DS annotation, missing OSGi import, classloader conflict. Always verify activation before proceeding.

```bash
# Replace ARTIFACT_ID with the Maven artifactId of the deployed bundle
ARTIFACT_ID="jahia-image-proxy"   # the global image proxy, or your own module

echo "Waiting for bundle activation..."
for i in $(seq 1 18); do
  STATE=$(docker exec "$JAHIA_CONTAINER" \
    curl -s "http://localhost:8080/modules/api/bundles" \
    -u "$JAHIA_USER:$JAHIA_PASS" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    bundles = json.load(sys.stdin)
    match = [b for b in bundles if '$ARTIFACT_ID' in b.get('symbolicName','')]
    print(match[0]['state'] if match else 'NOT_FOUND')
except:
    print('ERROR')
" 2>/dev/null)

  echo "  Attempt $i/18: bundle state = $STATE"

  if [ "$STATE" = "Active" ]; then
    echo "Bundle $ARTIFACT_ID is ACTIVE. Proceed."
    break
  fi

  sleep 5
done

if [ "$STATE" != "Active" ]; then
  echo "ERROR: Bundle $ARTIFACT_ID did not reach Active state after 90s."
  echo "Diagnose with:"
  echo "  docker logs $JAHIA_CONTAINER 2>&1 | grep -i '$ARTIFACT_ID' | tail -30"
  echo "  docker exec $JAHIA_CONTAINER curl -s http://localhost:8080/modules/api/bundles | python3 -c \"import json,sys; [print(b['symbolicName'], b['state']) for b in json.load(sys.stdin) if '$ARTIFACT_ID' in b.get('symbolicName','')]\""
  echo ""
  echo "Common causes:"
  echo "  - Bundle registered as Servlet.class instead of AbstractServletFilter.class (Jahia 8.2)"
  echo "  - Missing OSGi Import-Package entry"
  echo "  - @Reference service not available yet (wait longer)"
  echo "  - Java version mismatch (ensure JAVA_HOME points to Java 17)"
fi
```

**Note:** This check only applies to OSGi `.jar` deployments. For JS module deploys (`yarn jahia-deploy`), skip this step — JS modules do not appear in the Karaf bundle list.

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
curl -s -u $JAHIA_USER:$JAHIA_PASS \
  "$JAHIA_URL/modules/tools/definitionsBrowser.jsp" \
  | grep "ns:"
```

Or use the browser: `$JAHIA_URL/modules/tools/definitionsBrowser.jsp`

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
