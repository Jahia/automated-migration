---
name: 12-visual-diff
description: Screenshot every page of the reference site and the Jahia render side-by-side. Produces a per-page punch list of visual gaps. Run after all content is populated to verify ISO fidelity before declaring migration complete.
type: review
phase: 12
status: active
depends_on:
  - 9-create-content
allowed-tools: Bash, Read, Write, WebFetch
---

# Skill: Visual Diff

Takes full-page screenshots of every page on the reference site and its corresponding Jahia render, compares them, and produces a ranked punch list of visual gaps. This is the final ISO fidelity gate before declaring a migration complete.

> **Counts lie. Look at the render.** Never declare a component or page "done" from HTML grep counts or element tallies (`grep -c header-navigation` = 9 ✓). A count cannot see a transparent background, dark-on-dark text, a misplaced language switcher, a logo with no margin, a dropdown that pins to the viewport edge, or an icon rendering as an empty box. Those are exactly the defects a user spots in two seconds and then asks "why do I have to list all that?" The discipline: **render the actual page, screenshot it at 1440px (top / scrolled / hover states), open the image, and compare it to the reference image** — and inspect computed styles (`getComputedStyle`) for background/color/position when something looks off. Verify *before* reporting, not after the user complains. A passing build + non-zero element count is necessary, never sufficient.

---

## Agent identity
- **Agent name:** Mirrox
- **Reference style:** Mirror / reflection
- **Signature line (en):** *"Same page. Two renders. Find every pixel that disagrees."*
- **Personality note:** Relentless comparator. Never calls a match until both screens look identical at 1440px. Does not soften findings.
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

## Step 1: Build the page inventory

Read the site's content tree from JCR to get every live page URL:

```bash
curl -s -u $JAHIA_USER:$JAHIA_PASS \
  -H "Content-Type: application/json" \
  -H "Origin: $JAHIA_URL" \
  -X POST $JAHIA_URL/modules/graphql \
  -d '{
    "query": "{ jcr { nodeByPath(path: \"/sites/'"$JAHIA_SITE_KEY"'/home\") { descendants(typesFilter: {types: [\"jnt:page\"]}) { nodes { path name } } } } }"
  }' | python3 -c "
import json, sys
data = json.load(sys.stdin)
nodes = data['data']['jcr']['nodeByPath']['descendants']['nodes']
for n in nodes:
    print(n['path'])
" > /tmp/jahia-pages.txt

wc -l /tmp/jahia-pages.txt
cat /tmp/jahia-pages.txt
```

Also read the reference site's sitemap to build the URL pairs. If no sitemap, reconstruct from `workflow-output/content-data.json`:

```bash
python3 -c "
import json
data = json.load(open('workflow-output/content-data.json'))
for page in data.get('subPages', []):
    print(page.get('url', ''), page.get('slug', ''))
"
```

Build a mapping file `/tmp/page-pairs.json`:
```json
[
  {
    "slug": "home",
    "referenceUrl": "https://www.sialparis.com/fr-FR",
    "jahiaUrl": "http://localhost:8080/cms/render/live/fr/sites/SITEKEY/home.html"
  },
  {
    "slug": "sial-innovation",
    "referenceUrl": "https://www.sialparis.com/fr-FR/temps-forts/sial-innovation",
    "jahiaUrl": "http://localhost:8080/cms/render/live/fr/sites/SITEKEY/home/temps-forts/sial-innovation.html"
  }
]
```

Replace `SITEKEY` in the `jahiaUrl` values with `$JAHIA_SITE_KEY`, and `http://localhost:8080` with `$JAHIA_URL`.

---

## Step 1b: Empty area detection via page.preview (fast pre-check)

Before spending time on full-page screenshots, use `page.preview` to detect pages with empty areas. An empty area means content was never created there — it looks like a layout bug but is actually missing content.

```bash
source $(find . -name "migration.env" | head -1)

python3 - << 'EOF'
import subprocess, json, sys

with open('/tmp/jahia-pages.txt') as f:
    paths = [l.strip() for l in f if l.strip()]

import os
url = os.environ['JAHIA_URL']
user = os.environ['JAHIA_USER']
passwd = os.environ['JAHIA_PASS']

empty_pages = []
for path in paths:
    result = subprocess.run([
        'curl', '-s', '-X', 'POST', f'{url}/modules/mcp',
        '-u', f'{user}:{passwd}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "page.preview", "arguments": {"path": path, "locale": "fr"}}
        })
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    html = data.get('result',{}).get('content',[{}])[0].get('text','')
    empty_count = html.count('jahia-empty')
    if empty_count > 0:
        empty_pages.append((path, empty_count))
        print(f'EMPTY AREAS ({empty_count}): {path}')

if not empty_pages:
    print('All pages have content in all areas. Proceeding to screenshots.')
else:
    print(f'\n{len(empty_pages)} pages have empty areas — fix content before visual diff.')
    sys.exit(1)
EOF
```

**If any pages have empty areas: stop, go back to skill 09 and populate them.** Do not proceed to screenshots — an empty area screenshot is not a useful comparison.

---

## Step 2: Install screenshot tool if needed

```bash
# Check what is available
npx playwright --version 2>/dev/null && echo "playwright OK" || echo "playwright missing"
node -e "require('puppeteer'); console.log('puppeteer OK')" 2>/dev/null || echo "puppeteer missing"
```

If neither is available:
```bash
npm install -g puppeteer
```

---

## Step 3: Screenshot all pages

Create output directory:
```bash
mkdir -p /tmp/visual-diff
```

Log into Jahia once and reuse the session cookie across all pages:

```bash
node << EOF
const puppeteer = require('puppeteer');
const fs = require('fs');
const pairs = JSON.parse(fs.readFileSync('/tmp/page-pairs.json'));
const JAHIA_URL = process.env.JAHIA_URL || 'http://localhost:8080';
const JAHIA_USER = process.env.JAHIA_USER || 'root';
const JAHIA_PASS = process.env.JAHIA_PASS || 'root';

(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox'] });

  // Log into Jahia once
  const jahiaPage = await browser.newPage();
  await jahiaPage.setViewport({ width: 1440, height: 900 });
  await jahiaPage.goto(JAHIA_URL + '/cms/login', { waitUntil: 'networkidle2' });
  await jahiaPage.type('#username', JAHIA_USER);
  await jahiaPage.type('#password', JAHIA_PASS);
  await Promise.all([jahiaPage.waitForNavigation(), jahiaPage.keyboard.press('Enter')]);

  for (const pair of pairs) {
    const dir = '/tmp/visual-diff/' + pair.slug;
    fs.mkdirSync(dir, { recursive: true });

    // Reference screenshot
    const refPage = await browser.newPage();
    await refPage.setViewport({ width: 1440, height: 900 });
    try {
      await refPage.goto(pair.referenceUrl, { waitUntil: 'networkidle2', timeout: 30000 });
      await refPage.screenshot({ path: dir + '/reference.png', fullPage: true });
    } catch(e) {
      console.log('REFERENCE FAILED: ' + pair.slug + ' - ' + e.message);
    }
    await refPage.close();

    // Jahia screenshot (reuse authenticated session)
    await jahiaPage.goto(pair.jahiaUrl, { waitUntil: 'networkidle2', timeout: 30000 });
    await jahiaPage.screenshot({ path: dir + '/jahia.png', fullPage: true });

    console.log('DONE: ' + pair.slug);
  }

  await browser.close();
})();
EOF
```

---

### Step 3b: Mobile screenshots at 375px

After the desktop screenshots, take a second pass at 375px to catch mobile layout issues:

```bash
node << 'EOF'
const puppeteer = require('puppeteer');
const fs = require('fs');
const pairs = JSON.parse(fs.readFileSync('/tmp/page-pairs.json'));
const JAHIA_URL = process.env.JAHIA_URL || 'http://localhost:8080';
const JAHIA_USER = process.env.JAHIA_USER || 'root';
const JAHIA_PASS = process.env.JAHIA_PASS || 'root';

(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox'] });

  const jahiaPage = await browser.newPage();
  await jahiaPage.setViewport({ width: 375, height: 812, isMobile: true });
  await jahiaPage.goto(JAHIA_URL + '/cms/login', { waitUntil: 'networkidle2' });
  await jahiaPage.type('#username', JAHIA_USER);
  await jahiaPage.type('#password', JAHIA_PASS);
  await Promise.all([jahiaPage.waitForNavigation(), jahiaPage.keyboard.press('Enter')]);

  for (const pair of pairs) {
    const dir = '/tmp/visual-diff/' + pair.slug;
    fs.mkdirSync(dir, { recursive: true });

    const refPage = await browser.newPage();
    await refPage.setViewport({ width: 375, height: 812, isMobile: true });
    try {
      await refPage.goto(pair.referenceUrl, { waitUntil: 'networkidle2', timeout: 30000 });
      await refPage.screenshot({ path: dir + '/reference-mobile.png', fullPage: true });
    } catch(e) {
      console.log('MOBILE REF FAILED: ' + pair.slug + ' - ' + e.message);
    }
    await refPage.close();

    await jahiaPage.setViewport({ width: 375, height: 812, isMobile: true });
    await jahiaPage.goto(pair.jahiaUrl, { waitUntil: 'networkidle2', timeout: 30000 });
    await jahiaPage.screenshot({ path: dir + '/jahia-mobile.png', fullPage: true });

    console.log('MOBILE DONE: ' + pair.slug);
  }

  await browser.close();
})();
EOF
```

Add mobile checks to the gap checklist:
```
[ ] Navigation: collapses to hamburger on mobile / broken
[ ] Hero: text readable at 375px / overflows
[ ] Cards: stack to 1 column / stay multi-column (broken)
[ ] Images: scale correctly / overflow viewport
```

---

## Step 4: Compare each page pair

For each slug in `/tmp/visual-diff/`, view both screenshots and produce a structured gap report.

For every page, evaluate these dimensions in order:

### 4a: Above-the-fold check (first 900px)
- Hero present / missing
- Hero background image: present / blank / wrong image
- Hero heading text: matches reference / wrong / missing
- Navigation bar: correct / wrong layout / missing items
- Overall color/tone: matches / clearly different

### 4b: Layout structure check
- Number of sections: N reference vs N Jahia — match / mismatch
- Column layout per section: e.g. "2-col image+text" matches / is stacked
- Grid of cards: N cards per row matches reference / wrong count
- Proportions: sections look same height / one is compressed or stretched

### 4c: Content completeness check
- All text sections present / N sections missing
- All images present / N images showing as broken or blank
- All push cards present / N missing
- All CTAs/buttons present / styling matches

### 4d: Typography and color
- Headings: font family matches / clearly different
- Body text: size and weight match / noticeably different
- Button colors: match reference / wrong color
- Background colors: match / wrong

### 4e: Component-specific checks
- Navigation: all L1 items present, dropdowns work (for static check: all items visible)
- Footer: present and complete / missing sections

---

## Step 5: Produce the punch list

For each page with gaps, write to `workflow-output/visual-diff/<slug>-gaps.md`:

```markdown
# Visual Diff: sial-innovation

Reference: https://www.sialparis.com/fr-FR/temps-forts/sial-innovation
Jahia:     http://localhost:8080/cms/render/live/fr/sites/sial-paris/home/temps-forts/sial-innovation.html

## Critical (breaks ISO fidelity)
- [ ] Hero background image MISSING — reference has full-width photo, Jahia shows plain color
- [ ] Section 3 push cards: 4 cards in reference, only 2 visible in Jahia (content population incomplete)

## Layout (structure differs but content present)
- [ ] Section 2: reference is 2-col (image left, text right), Jahia is stacked (image above, text below)

## Minor (close but not exact)
- [ ] Hero heading font weight: reference is 800, Jahia appears ~700
- [ ] CTA button: reference has white border, Jahia has no border

## Matches
- Hero heading text: correct
- Navigation: all items present
- Footer: complete
```

Then produce a **global summary** at `workflow-output/visual-diff/SUMMARY.md`:

```markdown
# Visual Diff Summary

Pages compared: N
Pages with 0 gaps: K
Pages with gaps: M

## Critical gaps (fix before signoff)
- sial-innovation: hero image missing
- home: push cards section 3 incomplete (2/4 cards)
- le-salon: section 2 layout wrong (stacked instead of 2-col)

## Layout gaps (component-level fix needed)
- dates-et-acces: info cards column count wrong

## Minor gaps (CSS tweaks)
- All pages: heading font weight 800 vs 700
- All pages: CTA buttons missing white border

## Components to rebuild
- ns:imgContentBlock: needs CSS fix for 2-col layout at 1440px
- ns:pagesPushes: 4-col grid breaking at certain container widths

## Content to re-populate
- /home/temps-forts/sial-innovation/main: add 2 missing push card children
```

---

## Step 6: Fix loop

For each Critical gap:

1. **Missing image** → import via the image proxy, update the content node property, publish
2. **Wrong layout (stacked vs 2-col)** → fix the component's `.server.tsx` CSS classes, `yarn build && yarn jahia-deploy`, verify
3. **Missing content (wrong card count)** → re-populate the content node with the missing children, publish
4. **Wrong component used** → build the correct component, delete the wrong content node, re-add with correct type

After each fix, re-screenshot the affected page and verify the gap is closed.

---

## Step 6b: Performance baseline (Lighthouse)

After visual gaps are resolved, run a Lighthouse audit to capture Core Web Vitals before handing off to the client. This gives a concrete performance number to present and catches obvious regressions (missing image compression, render-blocking scripts, missing font-display).

### Install Lighthouse

```bash
npx lighthouse --version 2>/dev/null || npm install -g lighthouse
```

### Run against the live Jahia render

Lighthouse must run against the LIVE workspace URL, not default — only live has the published content and the clean render without jcontent toolbar overhead.

```bash
source $(find . -name "migration.env" | head -1)

mkdir -p workflow-output/lighthouse

# Audit home page
npx lighthouse "$JAHIA_URL/cms/render/live/fr/sites/$JAHIA_SITE_KEY/home.html" \
  --output json,html \
  --output-path workflow-output/lighthouse/home \
  --chrome-flags="--headless --no-sandbox" \
  --only-categories=performance,accessibility,seo \
  --quiet

# Extract scores
python3 - << 'EOF'
import json, glob

for f in glob.glob('workflow-output/lighthouse/*.report.json'):
    data = json.load(open(f))
    cats = data.get('categories', {})
    slug = f.replace('workflow-output/lighthouse/','').replace('.report.json','')
    perf = round(cats.get('performance',{}).get('score',0) * 100)
    a11y = round(cats.get('accessibility',{}).get('score',0) * 100)
    seo  = round(cats.get('seo',{}).get('score',0) * 100)
    print(f"{slug:30s}  perf={perf}  a11y={a11y}  seo={seo}")
EOF
```

### Run against key sub-pages

```bash
# Audit top 3 sub-pages (most visited or most content-heavy)
PAGES=(
  "home/exposer"
  "home/temps-forts/sial-innovation"
  "home/informations-pratiques"
)

for page in "${PAGES[@]}"; do
  slug=$(echo "$page" | tr '/' '-')
  npx lighthouse "$JAHIA_URL/cms/render/live/fr/sites/$JAHIA_SITE_KEY/${page}.html" \
    --output json \
    --output-path "workflow-output/lighthouse/$slug" \
    --chrome-flags="--headless --no-sandbox" \
    --only-categories=performance \
    --quiet 2>/dev/null
  echo "Done: $page"
done
```

### Interpret results

| Score | Status | Action |
|---|---|---|
| 90-100 | Green | No action needed |
| 70-89 | Orange | Note for client — not a blocker |
| 50-69 | Red | Fix before handoff |
| < 50 | Critical | Must fix |

**Common causes of low performance scores in Jahia migrations:**

- **Uncompressed images** (LCP impact): images imported via media.upload.url are not auto-compressed. If Lighthouse flags LCP > 2.5s, the hero image is usually the culprit. Compress via: `convert hero.jpg -quality 75 -resize 1920x hero-opt.jpg` and re-upload.
- **Render-blocking CSS** (TBT impact): all imported CSS is loaded synchronously in `<head>`. Split critical CSS (above-the-fold) from deferred CSS. Minimum fix: add `media="print" onload="this.media='all'"` to non-critical stylesheets.
- **No font-display** (CLS impact): imported `@font-face` declarations often lack `font-display: swap`. Add it to every `@font-face` block in the imported CSS.
- **Missing `<meta name="description">`** (SEO impact): add a `description (string) i18n` field to the page template CND and render it as `<meta name="description" content={...} />` in `Layout.tsx`.

### Write score to SUMMARY.md

Append Lighthouse scores to `workflow-output/visual-diff/SUMMARY.md`:

```bash
echo "" >> workflow-output/visual-diff/SUMMARY.md
echo "## Performance Baseline (Lighthouse)" >> workflow-output/visual-diff/SUMMARY.md
echo "" >> workflow-output/visual-diff/SUMMARY.md
python3 - << 'EOF'
import json, glob

for f in sorted(glob.glob('workflow-output/lighthouse/*.report.json')):
    data = json.load(open(f))
    cats = data.get('categories', {})
    slug = f.replace('workflow-output/lighthouse/','').replace('.report.json','')
    perf = round(cats.get('performance',{}).get('score',0) * 100)
    a11y = round(cats.get('accessibility',{}).get('score',0) * 100)
    seo  = round(cats.get('seo',{}).get('score',0) * 100)
    status = "green" if perf >= 90 else "orange" if perf >= 70 else "RED"
    print(f"- {slug}: perf={perf} ({status}), a11y={a11y}, seo={seo}")
EOF
>> workflow-output/visual-diff/SUMMARY.md
```

**Lighthouse scores are a baseline, not a gate.** A score of 65 on a Jahia instance running on a developer laptop behind VPN is not comparable to production. Present scores to the client with this caveat. Only block signoff if performance < 50 (indicates a structural problem, not environment noise).

---

## Step 7: Declare fidelity status

Only declare the migration ISO-complete when:

- [ ] 0 Critical gaps across all pages
- [ ] All hero background images populated (no plain-color heroes)
- [ ] All content grid counts match the reference (same number of cards/items)
- [ ] `workflow-output/visual-diff/SUMMARY.md` written and reviewed by user
- [ ] Lighthouse baseline run — scores written to workflow-output/visual-diff/SUMMARY.md
- [ ] No page scores below 50 on performance

Present the SUMMARY.md to the user and wait for explicit sign-off:

```
VISUAL DIFF COMPLETE

Pages compared:       N
ISO-complete pages:   K / N
Pages with critical gaps:  M

[paste SUMMARY.md here]

Type SIGNOFF to declare migration complete, or specify pages to fix.
```
