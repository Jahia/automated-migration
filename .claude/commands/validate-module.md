---
description: Validate CND namespace, syntax, build the module, deploy it, and confirm it reaches ACTIVE state. MANDATORY gate between step 5 and step 6.
---

# Module Validation Gate

This command runs a full validation pipeline before any site creation or content upload is allowed.

**You MUST pass every check below. If any check fails, STOP and fix the issue before proceeding.**

---

## Phase 1 — CND Syntax Validation (before touching Jahia)

### 1.1 Valid JCR property types only

Run this check against every `definition.cnd` file in the project:

```bash
# Find any use of invalid JCR types
grep -rn ' (richtext)' "$PROJECT_PATH/settings/definitions.cnd" "$PROJECT_PATH/src/components/" 2>/dev/null && echo "ERROR: 'richtext' is not a valid JCR type. Use '(string, richtext)' instead."

grep -rn ' (text)' "$PROJECT_PATH/settings/definitions.cnd" "$PROJECT_PATH/src/components/" 2>/dev/null && echo "ERROR: 'text' is not a valid JCR type. Use '(string)' instead."

grep -rn ' (int)' "$PROJECT_PATH/settings/definitions.cnd" "$PROJECT_PATH/src/components/" 2>/dev/null && echo "ERROR: 'int' is not a valid JCR type. Use 'long' instead."

grep -rn ' (float)' "$PROJECT_PATH/settings/definitions.cnd" "$PROJECT_PATH/src/components/" 2>/dev/null && echo "ERROR: 'float' is not a valid JCR type. Use 'double' instead."

grep -rn ' (integer)' "$PROJECT_PATH/settings/definitions.cnd" "$PROJECT_PATH/src/components/" 2>/dev/null && echo "ERROR: 'integer' is not a valid JCR type. Use 'long' instead."
```

**Valid JCR property types:** `string`, `binary`, `long`, `double`, `date`, `boolean`, `name`, `path`, `reference`, `weakreference`, `uri`, `decimal`

**Fix any error before continuing to Phase 2.**

### 1.2 Namespace declaration format

The main `settings/definitions.cnd` namespace URI must follow the Jahia module pattern:

```bash
# Extract namespace declarations and verify URI format
grep '^<[a-z]' "$PROJECT_PATH/settings/definitions.cnd" | grep -v 'www.jahia.org' | grep -v 'jnt\|jmix\|jdmix\|mix\|nt\|rep' && echo "WARNING: non-standard URI format detected above. Must be http://www.jahia.org/jahia/modules/<prefix>/nt/1.0"
```

Expected format for module namespaces:
- Content: `http://www.jahia.org/jahia/modules/<prefix>/nt/1.0`
- Mix: `http://www.jahia.org/jahia/modules/<prefix>/mix/1.0`

### 1.3 No namespace declarations in component definition.cnd files

Component-level CND files must NOT re-declare namespaces (they are inherited from `settings/definitions.cnd`):

```bash
grep -rn '^<[a-z]' "$PROJECT_PATH/src/components/" --include="definition.cnd" && echo "ERROR: namespace declarations found in component CND files — remove them, they belong only in settings/definitions.cnd"
```

---

## Phase 2 — Namespace Conflict Check Against Live Jahia

**This check MUST run before deployment.** A namespace already registered in Jahia with a different URI causes "prefix already declared" errors that prevent CND registration even if the module uploads successfully.

### 2.1 Extract module namespace declarations

```bash
# Get all namespace declarations from main CND
NAMESPACES=$(grep '^<[a-z]' "$PROJECT_PATH/settings/definitions.cnd" | grep -v 'jnt\|jmix\|jdmix\|mix =\|nt =\|rep =')
echo "Module namespaces to check:"
echo "$NAMESPACES"
```

### 2.2 Check registered namespaces via Groovy console

The GraphQL API does not expose a namespace list endpoint. Use the Groovy console instead.

Open http://localhost:8080/modules/tools/groovyConsole.jsp and run this script — it returns all non-standard namespaces as a string (Groovy `println` output is not captured; use `.collect().join()` pattern):

```groovy
import javax.jcr.NamespaceRegistry
import org.jahia.services.content.JCRSessionFactory

def session = JCRSessionFactory.getInstance().getCurrentSystemSession("default", null, null)
try {
    def registry = session.getWorkspace().getNamespaceRegistry()
    def standard = ['jnt','jmix','jdmix','mix','nt','rep','xml','xs','fn','sv','mode','jcr','j',
                    'jexchange','jahia','jgit','bootstrap','jstore','jcontent','jdata','jdrive'] as Set
    registry.prefixes.sort().findAll { prefix ->
        !standard.contains(prefix) && prefix.length() > 0
    }.collect { prefix ->
        "${prefix} -> ${registry.getURI(prefix)}"
    }.join('\n')
} finally {
    session.logout()
}
```

The result appears in the console output box. Copy the full list.

**Key insight:** `println` inside closures is not captured by the Groovy console result — always use `.collect { ... }.join('\n')` to return a string from the script body.

### 2.3 Cross-check for conflicts

For EACH namespace prefix declared in the module's `settings/definitions.cnd`, compare:
- **Module CND declares:** `<prefix = 'uri'>`
- **Jahia has registered:** `prefix -> uri` (from the Groovy output above)

**Conflict rules:**
- If prefix NOT in Jahia registry → **OK, safe to deploy**
- If prefix IS in registry with the SAME URI → **OK, safe to re-deploy** (idempotent)
- If prefix IS in registry with a DIFFERENT URI → **CONFLICT — STOP**

```
CONFLICT: prefix is registered with a different URI.
STOP. You must resolve before deploying.

Resolution A — Clear the stuck namespace:
  1. Go to http://localhost:8080/modules/tools/definitionsBrowser.jsp
  2. Find the Namespaces section
  3. Locate the conflicting prefix and remove it
  4. Restart the Jahia instance if the browser doesn't offer a remove action

Resolution B — Change the module prefix:
  1. Pick a prefix that has NEVER been registered (e.g. add a digit: sialparis2, sparis)
  2. Run: find "$PROJECT_PATH" -type f | xargs grep -l 'oldprefix' | while read f; do sed -i '' 's/oldprefix/newprefix/g' "$f"; done
  3. Verify settings/definitions.cnd, all definition.cnd files, all .tsx files, all .properties files
  4. Run yarn build to confirm no references remain
```

**If a CONFLICT is found: STOP. Do not deploy. Fix the conflict and re-run this validation from Phase 1.**

---

## Phase 3 — Build Verification

```bash
cd "$PROJECT_PATH"
yarn build 2>&1
BUILD_EXIT=$?
if [ $BUILD_EXIT -ne 0 ]; then
  echo "FAIL: yarn build failed. Fix TypeScript/Vite errors before deploying."
  exit 1
fi
echo "OK: build succeeded"
```

---

## Phase 4 — Deploy Module

Only run this after Phases 1-3 all pass.

```bash
cd "$PROJECT_PATH"
yarn jahia-deploy 2>&1
```

Wait for the command to complete and verify it shows "Operation successful" or equivalent success message.

**If the deploy output contains any error, STOP. Do not proceed to Phase 5.**

---

## Phase 5 — Verify Module is ACTIVE

A successful upload does NOT mean the module is active. CND types are only available when the OSGi bundle reaches ACTIVE state.

### 5.1 Check bundle state via Jahia console

Open the Groovy console at http://localhost:8080/modules/tools/groovyConsole.jsp and run:

```groovy
import org.osgi.framework.Bundle
def context = org.springframework.web.context.ContextLoader.getCurrentWebApplicationContext()
def bundleContext = context.getBean("org.springframework.osgi.context.BundleContextAware")?.bundleContext
if (!bundleContext) {
    bundleContext = org.jahia.osgi.BundleUtils.getBundleContext()
}
bundleContext.bundles.findAll { it.symbolicName?.contains('MODULE_NAME') }.each { b ->
    println "${b.symbolicName} — state: ${b.state} (${['UNINSTALLED','INSTALLED','RESOLVED','STARTING','STOPPING','ACTIVE'][b.state - 1]})"
}
```

Replace `MODULE_NAME` with the module's symbolic name (from `package.json`'s `jahia.name` field).

**Expected state:** `ACTIVE` (state = 32)

If state is `INSTALLED` or `RESOLVED`: the module uploaded but failed to start. Read the OSGi console logs for the reason.

### 5.2 Verify CND types are queryable via GraphQL

For the primary content type of the module (e.g. the main page component), run:

```bash
# Replace sialparis:heroCarousel with an actual type from this module
MODULE_TYPE="sialparis:heroCarousel"

curl -s -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Origin: $JAHIA_URL" \
  -H "Content-Type: application/json" \
  "$JAHIA_URL/modules/graphql" \
  -X POST \
  -d "{\"query\":\"{ jcr { nodesByQuery(query: \\\"SELECT * FROM [${MODULE_TYPE}] LIMIT 1\\\", queryLanguage: JCR_SQL2) { nodes { path } } } }\"}" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
errors = data.get('errors', [])
if errors:
    for e in errors:
        msg = e.get('message', '')
        if 'node type does not exist' in msg or 'Unknown type' in msg:
            print(f'FAIL: type not registered — {msg}')
            print('The module is not ACTIVE or the CND failed to parse.')
        else:
            print(f'FAIL: GraphQL error — {msg}')
else:
    print(f'OK: type {\"$MODULE_TYPE\"!r} is registered and queryable')
"
```

**If FAIL: do not proceed. The module is not in a valid state.**

---

## Phase 6 — Update State

Only after all phases pass:

```bash
STATE="$PROJECT_PATH/workflow-output/state.json"
if [ -f "$STATE" ]; then
  jq --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
     '.steps["5.5-validate"] = {"status": "completed", "completedAt": $ts, "notes": "namespace OK, build OK, deploy OK, module ACTIVE, types queryable"}' \
     "$STATE" > /tmp/state.tmp && mv /tmp/state.tmp "$STATE"

  cat >> "$PROJECT_PATH/workflow-output/migration-log.md" << EOF

## [$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Step 5.5 — Module Validation — COMPLETED
- **Namespace check:** PASS
- **Build:** PASS
- **Deploy:** PASS
- **Module state:** ACTIVE
- **Types queryable:** PASS
- **Next step:** /6-content is now unlocked
EOF
fi

echo ""
echo "=========================================="
echo "ALL VALIDATION CHECKS PASSED"
echo "The module is deployed, ACTIVE, and CND types are registered."
echo "You may now proceed to /6-content"
echo "=========================================="
```

---

## Common failures and fixes

| Error | Cause | Fix |
|---|---|---|
| `prefix already declared` | Namespace prefix stuck in JCR registry from previous failed deploy | Clear via http://localhost:8080/modules/tools/definitionsBrowser.jsp OR use a fresh prefix that was never registered |
| `uri already declared` | Namespace URI already used by another prefix | Change the URI to match the pattern `http://www.jahia.org/jahia/modules/<unique-prefix>/nt/1.0` |
| `Unknown type 'richtext'` | `(richtext)` used as a bare JCR type | Change to `(string, richtext)` |
| `Unknown type 'text'` | `(text)` used as a bare JCR type | Change to `(string)` |
| `jmix:cache` in CND | Does not exist in Jahia 8.2 — causes "Error registering node type definition" | Remove `jmix:cache` from all list type supertypes; `jmix:list` and `jmix:renderableList` are sufficient |
| Module INSTALLED not ACTIVE | Missing OSGi dependency, classpath error, or CND parse failure | Read Karaf logs in Docker: `docker logs <container> 2>&1 | grep -A5 'sial-paris\|ERROR'` |
| Type not queryable after ACTIVE | CND parse failure during bundle activation | Check Karaf logs for `ParseException`; fix and redeploy |
