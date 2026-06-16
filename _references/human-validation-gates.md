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

## Gate 3 — Shell layout review (after `08-page-templates`)

**Stop after:** `Layout.tsx` and page template variants are deployed and the module is ACTIVE.

**Show the user:** A screenshot of the deployed page at this stage — header and footer rendered, main area empty. This is a structural check only, not a visual fidelity check.

**Wait for:** User confirms header/footer are present and the page structure is correct (no JS errors, no broken layout shell).

**Why:** Layout changes after content is placed are disruptive. This gate catches structural issues (wrong AbsoluteArea names, missing header, broken grid) before content creation begins.

**What to check:**
- Header renders (logo, navigation visible)
- Footer renders
- No JavaScript console errors
- Page does not 500

**What NOT to check at this gate:** Visual fidelity to the original — components have no content yet. Save that for Gate 4.

---

## Gate 4 — Visual fidelity review (after `09-create-content`)

**Stop after:** All home page content is created and published to LIVE.

**This is the primary visual quality gate.** Do not declare the migration done until this gate passes.

**Show the user — side by side:**
1. Screenshot of the **original site** at 1440px (saved during step 1 as `workflow-output/screenshots/reference-home-1440.png`)
2. Screenshot of the **Jahia render** at 1440px (taken now via Chrome MCP)
3. Screenshot of original at 375px vs Jahia at 375px

**Automated checks before presenting screenshots:**
```bash
JAHIA_URL=$(jq -r '.server.url' "$STATE")
SITE_KEY=$(jq -r '.siteKey' "$STATE")

# 1. HTTP 200 on live page
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "$JAHIA_URL/sites/$SITE_KEY/home.html")
[ "$HTTP" = "200" ] || echo "FAIL: live page returned HTTP $HTTP"

# 2. No broken images (404 on any <img src>)
curl -s "$JAHIA_URL/sites/$SITE_KEY/home.html" | \
  grep -oE 'src="[^"]+"' | grep -v 'data:' | \
  while read src; do
    url=$(echo $src | sed 's/src="//;s/"//')
    [[ "$url" != http* ]] && url="$JAHIA_URL$url"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    [ "$STATUS" != "200" ] && echo "BROKEN IMAGE: $url ($STATUS)"
  done

# 3. No raw i18n keys visible (missing translations)
curl -s "$JAHIA_URL/sites/$SITE_KEY/home.html" | grep -oE '[a-z]+_[a-zA-Z]+\.[a-zA-Z\.]+' | head -10
```

**Save Jahia screenshot:**
```
workflow-output/screenshots/jahia-home-1440.png
workflow-output/screenshots/jahia-home-375.png
```

**Wait for:** User to visually compare original vs Jahia render and type VALIDATED or describe what to fix.

**Why:** Curl HTTP 200 does not detect broken images, collapsed components, missing CSS, wrong fonts, or layout regressions. Only a browser screenshot comparison catches visual failures.

---

## Gate 5 — Review sign-off (after `10-review`)

**Stop after:** The review skill reports all critical violations.

**Show the user:** The full review output (critical, warnings, suggestions).

**Wait for:** User to decide which violations to fix now vs defer.

**Why:** Some review findings require product decisions (e.g. "should the tag cloud use jmix:tagged or a custom field?"). Agents should not auto-fix CND schema decisions.
