---
description: Import CSS, JS, fonts, and assets from a downloaded website into the static folder
---

## State management (run at start and end)

**At the START of this step — PREREQUISITE CHECK:**
```bash
STATE="$PROJECT_PATH/workflow-output/state.json"

# 1. Verify state.json exists
[ -f "$STATE" ] || { echo "ERROR: state.json missing — run /2-scaffold first"; exit 1; }

# 2. Verify step 1-analyze is completed (if analysis was already run)
ANALYZE_STATUS=$(jq -r '.steps["1-analyze"].status' "$STATE")
# Note: 1-analyze may be "pending" if scaffold ran first — that is OK.
# If it is "failed", stop.
[ "$ANALYZE_STATUS" = "failed" ] && { echo "ERROR: step 1-analyze failed — fix before continuing"; exit 1; }

# 3. Mark in_progress
jq '.steps["3-assets"].status = "in_progress"' "$STATE" > /tmp/state.tmp && mv /tmp/state.tmp "$STATE"
```

**At the END of this step:**
```bash
# 1. Count imported files
CSS_COUNT=$(find "$PROJECT_PATH/static/css" -type f 2>/dev/null | wc -l | tr -d ' ')
JS_COUNT=$(find "$PROJECT_PATH/static/js" -type f 2>/dev/null | wc -l | tr -d ' ')
FONT_COUNT=$(find "$PROJECT_PATH/static/fonts" -type f 2>/dev/null | wc -l | tr -d ' ')
ASSET_COUNT=$(find "$PROJECT_PATH/static/assets" -type f 2>/dev/null | wc -l | tr -d ' ')

# 2. Update state.json
jq --arg notes "${CSS_COUNT} css, ${JS_COUNT} js, ${FONT_COUNT} fonts, ${ASSET_COUNT} images" \
   --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
   '.steps["3-assets"] = {"status": "completed", "completedAt": $ts, "notes": $notes}' \
   "$STATE" > /tmp/state.tmp && mv /tmp/state.tmp "$STATE"

# 3. Append to migration-log.md
cat >> "$PROJECT_PATH/workflow-output/migration-log.md" << EOF

## [$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Step 3 — Import Assets — COMPLETED
- **Imported:** ${CSS_COUNT} css, ${JS_COUNT} js, ${FONT_COUNT} fonts, ${ASSET_COUNT} images
EOF
```

---

Import all static assets from the source website into the module's `static/` folder.

## Overview

Target structure:
```
static/
├── css/         # Stylesheets
├── js/          # JavaScript files
├── fonts/       # Font files (woff, woff2, ttf, otf, eot)
└── assets/      # Images and other media
```

## Instructions

### Step 1: Determine source

- Argument provided → URL (download) or local path (use directly)
- No argument → check `/tmp/website-download/` from `/1-analyze`
- Neither → ask user

### Step 2: Download if URL

```bash
mkdir -p /tmp/website-download
wget --recursive --level=2 --no-parent --convert-links \
     --adjust-extension --page-requisites --no-clobber \
     --user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
     --directory-prefix=/tmp/website-download "{URL}"

SOURCE_PATH=$(find /tmp/website-download -type d -mindepth 1 -maxdepth 1 | head -1)
```

### Step 3: Find project directory

```bash
find . -maxdepth 3 -name "definitions.cnd" -path "*/settings/*" | head -1
```

Use the grandparent as PROJECT_DIR.

### Step 4: Create static structure

```bash
mkdir -p $PROJECT_DIR/static/{css,js,fonts,assets}
```

### Step 5: Copy assets

```bash
# CSS
find "$SOURCE_PATH" -type f -name "*.css" ! -name "*.min.css" | while read f; do
  cp "$f" "$PROJECT_DIR/static/css/"
done

# JS
find "$SOURCE_PATH" -type f -name "*.js" ! -name "*.min.js" | while read f; do
  cp "$f" "$PROJECT_DIR/static/js/"
done

# Fonts
find "$SOURCE_PATH" -type f \( -name "*.woff" -o -name "*.woff2" -o -name "*.ttf" -o -name "*.eot" -o -name "*.otf" \) | while read f; do
  cp "$f" "$PROJECT_DIR/static/fonts/"
done

# Images
find "$SOURCE_PATH" -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.gif" -o -name "*.svg" -o -name "*.webp" \) | while read f; do
  cp "$f" "$PROJECT_DIR/static/assets/"
done
```

### Step 6: Extract inline styles and scripts

From the downloaded HTML, extract `<style>` blocks → `static/css/inline.css` and `<script>` blocks (without `src`) → `static/js/inline.js`.

### Step 7: Wire into Layout.tsx

Add `<AddResources>` entries in this order (inline FIRST):

```tsx
import { AddResources, buildModuleFileUrl } from "@jahia/javascript-modules-library";

// In Layout <head>:
<AddResources type="css" resources={buildModuleFileUrl("static/css/inline.css")} />
<AddResources type="css" resources={buildModuleFileUrl("static/css/main.css")} />
// ... other CSS files ...
<AddResources type="javascript" resources={buildModuleFileUrl("static/js/inline.js")} />
// ... other JS files ...
```

Never hardcode `/modules/<name>/...` — always use `buildModuleFileUrl`.

### Step 8: Verify

```bash
grep -n "inline.css" $PROJECT_DIR/src/templates/Layout.tsx
grep -n "inline.js" $PROJECT_DIR/src/templates/Layout.tsx
```

Both must return results. If not, the inline assets are not loaded and the site will be missing critical styles.

### Step 9: Report

Count files by category and show totals. Next: `/4-templates`.
