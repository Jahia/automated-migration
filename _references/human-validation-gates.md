# Human Validation Gates

These are the points in the migration workflow where the agent **must stop and wait for human confirmation** before proceeding. An agent that skips a gate risks irreversible work or misaligned output.

---

## Gate 0 — Jahia server connection (before any work)

**Stop at:** The very start, before analysis, scaffolding, or any file creation.

**Ask the user for:**
- Jahia URL (e.g. `http://localhost:8080`)
- Username
- Password

**Then verify immediately:**
```bash
HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Origin: $JAHIA_URL" \
  "$JAHIA_URL/modules/graphql")
```

**Gate passes when:** HTTP response is `200` or `400` (400 = GraphQL endpoint reachable, no query sent yet — that is correct).

**Gate fails when:** `000` (connection refused / wrong URL), `401` (wrong credentials), `403` (insufficient permissions). Ask again. Do not proceed.

**Wait for:** A successful connection response before touching any file or starting analysis.

**Why:** Every subsequent step calls Jahia — analysis (site detection), scaffold (siteKey lookup), validate-module (ACTIVE check), create-content (mutations). A wrong URL or wrong password discovered at step 6 wastes the entire session.

---

## Gate 1 — Component manifest review (after `01-analyze-website`)

**Stop after:** The component manifest is produced (list of sections + proposed content types).

**Show the user:**
- The numbered section map (e.g. `[1] HERO — animated text + CTA`)
- The proposed CND field split for each component
- The dependency list (CSS libs, JS animations, fonts)

**Wait for:** User to confirm the component list, approve field splits, and confirm which dependencies to import.

**Why:** Proceeding with the wrong component scope wastes all downstream build time. Field split corrections are 5x cheaper at this stage than after CND + view are written.

---

## Gate 2 — Scaffold confirmation (after `02-scaffold-module`)

**Stop after:** The module is scaffolded and `yarn install` completes.

**Show the user:**
- The module directory structure
- The namespace chosen (e.g. `ns:`)
- The `package.json` name and version

**Wait for:** User to confirm namespace and module name before any CND or component is written.

**Why:** The namespace is baked into every CND definition, every view registration, every resource bundle key. Changing it later requires touching 50+ files.

---

## Gate 3 — Template layout review (after `08-page-templates`)

**Stop after:** `Layout.server.tsx` and page template variants are implemented.

**Show the user:** The deployed page rendered in the browser (use `/jahia-dev-screenshot` if available).

**Wait for:** User visual approval of the layout shell before content is filled in.

**Why:** Layout changes after content is placed are disruptive — every component may need re-placed or re-styled.

---

## Gate 4 — Content review (after `09-create-content`)

**Stop after:** Pages and content nodes are created, published, and visible on the live site.

**Show the user:**
- A list of created nodes with their JCR paths
- The live URL for each page

**Wait for:** User to spot-check a representative set of pages before declaring the migration complete.

**Why:** Bulk content creation via GraphQL can silently create nodes with wrong types or missing translations. Human spot-check is faster than automated validation at this stage.

---

## Gate 5 — Review sign-off (after `10-review`)

**Stop after:** The review skill reports all critical violations.

**Show the user:** The full review output (critical, warnings, suggestions).

**Wait for:** User to decide which violations to fix now vs defer.

**Why:** Some review findings require product decisions (e.g. "should the tag cloud use jmix:tagged or a custom field?"). Agents should not auto-fix CND schema decisions.
