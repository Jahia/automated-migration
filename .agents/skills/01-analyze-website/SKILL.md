---
name: 1-analyze-website
description: Crawl a website, cluster recurring HTML patterns across ALL pages to identify reusable Jahia components, assign views per component, and produce a verified component manifest + content data. Use at the start of every migration.
type: workflow
phase: 1
status: active
invokes_workflow: true
depends_on:
  - 2-scaffold-module
allowed-tools: Bash, Read, Write, WebFetch
---

# Skill: Analyze Website

Turns a website into a structured Jahia component blueprint by clustering HTML patterns across the full page corpus — not just the home page.

> ⚠️ **Capture from the live site FIRST (browser-first).** For JS-rendered or
> WAF'd sites the wget/curl cache is only the static shell — listings, facet
> values, full article bodies, the complete item list, and real image URLs are
> NOT in it. Run **`/capture-reference`** (`.agents/skills/capture-reference/SKILL.md`)
> before clustering/modelling, and build `content-data.json` from the captured
> truth. Never fabricate content/titles/taxonomy/images from a partial cache.

---

## Agent identity
- **Agent name:** Archaeon
- **Reference style:** Archaeology / excavation
- **Signature line (en):** *"Every site hides a component. I find them all."*
- **Personality note:** Methodical and thorough. Documents everything before recommending anything. Never skips a section.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## Jahia concepts this skill must apply

### Content types and views

A **content type** (CND node type) defines the structured data — fields, mixins, constraints. A **view** defines how that data is rendered. One content type can have multiple views. Views are selected by name at render time.

Standard view naming convention:

| View file name | When Jahia uses it |
|---|---|
| `default.server.tsx` | Default rendering — used in page areas, listing cards, inline placement |
| `fullPage.server.tsx` | Full-page rendering — only for `jmix:mainResource` content |
| `card.server.tsx` | Compact card for use inside a listing component |
| `featured.server.tsx` | Featured/highlighted variant (e.g. first item in a grid) |

**Rule — `jmix:mainResource` always needs TWO views:**
- `default.server.tsx` — the card/teaser rendered inside a listing component or area
- `fullPage.server.tsx` — the full detail page rendered when the content URL is accessed directly (e.g. `/sites/mysite/contents/news/my-article.html`)

Without `fullPage.server.tsx`, clicking through to a mainResource content item shows a blank page. The full-page view renders the complete article/product/event layout — hero image, body copy, metadata, related items — using the same CND fields.

### When to assign jmix:mainResource

A content type needs `jmix:mainResource` when:
- It has its own navigable URL (news article, event, product, team member, case study)
- The site links to it directly from listing pages or navigation
- It is stored in a content folder (`jnt:contentFolder`), not in a page area

It does NOT need `jmix:mainResource` when:
- It only ever appears inside a page area (hero, banner, CTA block, push card)
- It is a child node managed inside a container (list item, carousel slide)

---

## Prerequisites: migration.env must exist

Before doing anything, verify the migration environment has been configured:

```bash
find . -name "migration.env" | head -1
```

If `migration.env` does not exist: **STOP. Tell the user to run `/0-migration-start` first.** Do not guess URLs or credentials.

If it exists, load it:
```bash
source $(find . -name "migration.env" | head -1)
echo "Jahia: $JAHIA_URL | Site: $JAHIA_SITE_KEY | MCP: $MCP_AVAILABLE"
```

---

## Step 0: Bootstrap the image proxy (MANDATORY — do this before any crawl)

Every migration imports images from an external CDN into Jahia DAM. Without a running image proxy in Jahia, image import will fail or require manual work. This step ensures the proxy is deployed and responding before analysis begins.

### Why this is required

External site images are served from CDNs (Cloudflare, Akamai, Sitecore SXA `/–/media/`, etc.). Those CDNs often:
- Require `?rev=` or similar query tokens that expire
- Block direct `wget` / `curl` from headless environments
- Return different content-types than expected

The Jahia image proxy solves this by running inside Jahia itself — it fetches the image server-side using a Java `HttpURLConnection` (which passes CDN checks), stores it as a `jnt:file` in DAM, and publishes it to the live workspace in one call.

### 0a: Check if the proxy is already deployed

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8080/modules/jahia-image-proxy/import-image?sourceUrl=test"
```

- HTTP 400 (bad request) → proxy is running, missing params as expected. **Skip to step 0d.**
- HTTP 404 → proxy not deployed. Continue with step 0b.
- Connection refused → Jahia not running. Fix that first.

### 0b: Create the proxy module

The canonical proxy module lives at:
```
jahiaMigration/projects/jahia-image-proxy/
```

Check if it already exists:
```bash
ls jahiaMigration/projects/jahia-image-proxy/pom.xml 2>/dev/null && echo EXISTS || echo MISSING
```

If MISSING, create it now. The module is a generic, site-agnostic proxy — it imports images from any external URL into any JCR path. It must NOT be named after any specific migration project.

**pom.xml** — `jahiaMigration/projects/jahia-image-proxy/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.jahia.modules</groupId>
        <artifactId>jahia-modules</artifactId>
        <version>8.2.0.0</version>
        <relativePath/>
    </parent>

    <groupId>com.jahia.tools</groupId>
    <artifactId>jahia-image-proxy</artifactId>
    <version>1.0.0</version>
    <packaging>bundle</packaging>
    <name>Jahia Image Proxy</name>
    <description>Generic proxy: fetches images from external URLs and imports them into Jahia DAM.</description>

    <properties>
        <jahia.plugin.version>6.9</jahia.plugin.version>
        <require-capability>osgi.extender;filter:="(osgi.extender=org.jahia.bundles.blueprint.extender.config)"</require-capability>
    </properties>

    <repositories>
        <repository>
            <id>jahia-public</id>
            <url>https://devtools.jahia.com/nexus/content/groups/public</url>
            <releases><enabled>true</enabled></releases>
            <snapshots><enabled>true</enabled></snapshots>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>org.jahia.server</groupId>
            <artifactId>jahia-impl</artifactId>
            <version>8.2.0.7</version>
            <scope>provided</scope>
            <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
        </dependency>
        <dependency>
            <groupId>org.jahia.server</groupId>
            <artifactId>jahia-api</artifactId>
            <version>8.2.0.7</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>javax.jcr</groupId>
            <artifactId>jcr</artifactId>
            <version>2.0</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>javax.servlet</groupId>
            <artifactId>javax.servlet-api</artifactId>
            <version>3.1.0</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.osgi</groupId>
            <artifactId>org.osgi.service.component.annotations</artifactId>
            <version>1.4.0</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>1.7.36</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.felix</groupId>
                <artifactId>maven-bundle-plugin</artifactId>
                <extensions>true</extensions>
                <configuration>
                    <instructions>
                        <Bundle-SymbolicName>${project.artifactId}</Bundle-SymbolicName>
                        <Import-Package>
                            org.jahia.services.content,
                            org.jahia.services.content.decorator,
                            org.jahia.bin.filters,
                            javax.jcr,
                            javax.servlet,
                            javax.servlet.http,
                            org.slf4j,
                            !org.osgi.service.component.annotations,
                            *
                        </Import-Package>
                        <Export-Package/>
                    </instructions>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Java source** — `jahiaMigration/projects/jahia-image-proxy/src/main/java/com/jahia/tools/proxy/ImageProxyServlet.java`:

```java
package com.jahia.tools.proxy;

import org.jahia.bin.filters.AbstractServletFilter;
import org.jahia.services.content.*;
import org.osgi.service.component.annotations.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.jcr.Binary;
import javax.jcr.RepositoryException;
import javax.servlet.*;
import javax.servlet.http.*;
import java.io.*;
import java.net.*;

/**
 * Generic image proxy for Jahia migrations.
 *
 * Endpoint: GET/POST /modules/jahia-image-proxy/import-image
 *
 * Required params:
 *   sourceUrl  - external image URL to fetch
 *   destPath   - absolute JCR folder path (e.g. /sites/mysite/files/imported-images)
 *   filename   - target filename (e.g. hero-banner.jpg)
 *
 * Optional params:
 *   referer    - Referer header to send when fetching the image (helps bypass CDN checks)
 *
 * Returns JSON: {"success":true,"jcrPath":"...","url":"/files/live/..."}
 *
 * Registered as AbstractServletFilter (required for Jahia 8.2 — Servlet.class registration fails).
 */
@Component(service = AbstractServletFilter.class, immediate = true)
public class ImageProxyServlet extends AbstractServletFilter {

    private static final Logger log = LoggerFactory.getLogger(ImageProxyServlet.class);
    private static final String PATH = "/modules/jahia-image-proxy/import-image";

    @Reference private JCRTemplate jcrTemplate;
    @Reference private JCRPublicationService publicationService;

    @Activate
    protected void activate() {
        setUrlPatterns(new String[]{PATH});
        setOrder(10f);
    }

    @Override public void init(FilterConfig cfg) {}
    @Override public void destroy() {}

    @Override
    public void doFilter(ServletRequest req, ServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest  hreq  = (HttpServletRequest) req;
        HttpServletResponse hresp = (HttpServletResponse) res;
        if (!hreq.getRequestURI().contains(PATH)) { chain.doFilter(req, res); return; }

        String sourceUrl = hreq.getParameter("sourceUrl");
        String destPath  = hreq.getParameter("destPath");
        String filename  = hreq.getParameter("filename");
        String referer   = hreq.getParameter("referer");

        hresp.setContentType("application/json;charset=UTF-8");

        if (sourceUrl == null || destPath == null || filename == null) {
            hresp.setStatus(400);
            hresp.getWriter().write("{\"error\":\"Missing required params: sourceUrl, destPath, filename\"}");
            return;
        }

        filename = filename.replaceAll("[^a-zA-Z0-9._-]", "-");

        try {
            byte[] bytes    = fetch(sourceUrl, referer);
            String mime     = mimeFor(filename);
            final String fn = filename;
            final byte[] fb = bytes;
            final String fm = mime;

            String[] result = jcrTemplate.doExecuteWithSystemSession(session -> {
                String jcrPath = store(session, destPath, fn, fb, fm);
                String uuid    = session.getNode(jcrPath).getIdentifier();
                return new String[]{jcrPath, uuid};
            });

            publicationService.publishByMainId(result[1]);

            hresp.setStatus(200);
            hresp.getWriter().write(
                "{\"success\":true,\"jcrPath\":\"" + result[0] +
                "\",\"url\":\"/files/live" + result[0] + "\"}"
            );
            log.info("Imported {} -> {}", sourceUrl, result[0]);

        } catch (Exception e) {
            log.error("Import failed for {}", sourceUrl, e);
            hresp.setStatus(500);
            hresp.getWriter().write("{\"error\":\"" + esc(e.getMessage()) + "\"}");
        }
    }

    private byte[] fetch(String url, String referer) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod("GET");
        c.setRequestProperty("User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36");
        if (referer != null) c.setRequestProperty("Referer", referer);
        c.setConnectTimeout(15_000);
        c.setReadTimeout(30_000);
        c.setInstanceFollowRedirects(true);
        int status = c.getResponseCode();
        if (status != 200) throw new IOException("HTTP " + status + " for " + url);
        try (InputStream is = c.getInputStream()) { return is.readAllBytes(); }
    }

    private String store(JCRSessionWrapper session, String destPath, String filename,
                         byte[] bytes, String mime) throws RepositoryException {
        JCRNodeWrapper folder;
        try {
            folder = session.getNode(destPath);
        } catch (javax.jcr.PathNotFoundException e) {
            folder = mkdirs(session, destPath);
        }
        if (folder.hasNode(filename)) { folder.getNode(filename).remove(); session.save(); }
        JCRNodeWrapper file    = folder.addNode(filename, "jnt:file");
        JCRNodeWrapper content = file.addNode("jcr:content", "jnt:resource");
        Binary bin = session.getValueFactory().createBinary(new ByteArrayInputStream(bytes));
        content.setProperty("jcr:data", bin);
        content.setProperty("jcr:mimeType", mime);
        content.setProperty("jcr:lastModified", java.util.Calendar.getInstance());
        session.save();
        return file.getPath();
    }

    private JCRNodeWrapper mkdirs(JCRSessionWrapper session, String path) throws RepositoryException {
        String[] parts = path.split("/");
        StringBuilder cur = new StringBuilder();
        JCRNodeWrapper node = null;
        for (String p : parts) {
            if (p.isEmpty()) continue;
            cur.append("/").append(p);
            try { node = session.getNode(cur.toString()); }
            catch (javax.jcr.PathNotFoundException e) {
                if (node == null) throw new RepositoryException("Root not found: " + cur);
                node = node.addNode(p, "jnt:folder");
            }
        }
        session.save();
        return node;
    }

    private String mimeFor(String f) {
        String l = f.toLowerCase();
        if (l.endsWith(".png"))  return "image/png";
        if (l.endsWith(".gif"))  return "image/gif";
        if (l.endsWith(".webp")) return "image/webp";
        if (l.endsWith(".svg"))  return "image/svg+xml";
        return "image/jpeg";
    }

    private String esc(String s) {
        if (s == null) return "null";
        return s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n");
    }
}
```

### 0c: Build and deploy the proxy

```bash
# Always use Java 17 — Homebrew default is Java 25 and breaks Maven builds
export JAVA_HOME=$(/usr/libexec/java_home -v 17)

cd jahiaMigration/projects/jahia-image-proxy
mvn clean package -q

# Find the running Jahia container name
CONTAINER=$(docker ps --format '{{.Names}}' | grep -i jahia | head -1)
echo "Deploying to container: $CONTAINER"

docker cp target/jahia-image-proxy-1.0.0.jar $CONTAINER:/var/jahia/karaf/deploy/
```

Wait 10 seconds for OSGi activation, then verify:

```bash
sleep 10
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8080/modules/jahia-image-proxy/import-image?sourceUrl=test"
# Expected: 400 (bad request = proxy is alive and parsed the request)
```

If HTTP 404 after 10s, wait another 20s and retry — OSGi bundle activation can be slow on first deploy.

### 0d: Record the proxy base URL

For the rest of the migration, images are imported via:

```
http://localhost:8080/modules/jahia-image-proxy/import-image
  ?sourceUrl=<external-image-url>
  &destPath=/sites/<siteKey>/files/imported-images/<subfolder>
  &filename=<sanitized-filename.jpg>
  &referer=<site-homepage-url>   ← optional, helps with CDN auth
```

The `referer` parameter is useful when the CDN checks `Referer` headers (common on Sitecore SXA and Contentful CDNs). Pass the site's homepage URL as `referer`.

After a successful import the endpoint returns:
```json
{ "success": true, "jcrPath": "/sites/mysite/files/imported-images/...", "url": "/files/live/..." }
```

Use the `url` value as the image path in content nodes — it is the live workspace URL.

---

## Scraping policy (applies to every fetch in this skill — non-negotiable)

Reference sites sit behind CDNs/WAFs (Cloudflare, Akamai) and you may be on a VPN the WAF distrusts. Three rules, enforced by the shared helper `orchestration/lib/cached-fetch.sh` — always scrape through it, never with a bare `wget`/`curl`:

0. **ALWAYS check the cache before scraping again.** Before *any* fetch — `curl` **or** browser capture — check `<project>/.reference/cache/`. If the URL is already cached, reuse it; do not re-hit the origin. This is the first thing every scrape step does. (The `fetch`/`crawl` commands do it automatically; for the browser path, call `get` first — see below.)
1. **Cache everything locally, fetch once.** All scraped HTML/text/assets are written under **`<project>/.reference/cache/`** (in-project, durable — survives sessions, compaction and re-runs). Re-running a migration must not re-scrape.
2. **Slow down when blocked — never hammer.** A polite base delay sits between requests; on any WAF/rate-limit signal (HTTP 403/429/5xx/520-524 or a Cloudflare challenge body) back off exponentially and raise the delay for the rest of the run. After a few attempts, **stop** and fall back to browser capture.

```bash
FETCH="orchestration/lib/cached-fetch.sh"   # from repo root

# Cache-first check (READ-ONLY, no network). exit 0 + prints path if cached; exit 3 if not.
"$FETCH" get "$PROJECT_PATH" "$URL" && echo "already cached — reuse it"

# Fetch a page (checks cache first automatically; only hits network on a miss; backs off on WAF):
"$FETCH" fetch "$PROJECT_PATH" "https://www.example.com/fr-FR/some-page"
# Throttle harder when a site is blocking: RATE_DELAY (base s), MAX_ATTEMPTS
RATE_DELAY=8 MAX_ATTEMPTS=8 "$FETCH" fetch "$PROJECT_PATH" "$URL"
# Force a re-scrape of an already-cached URL (rare; deliberate escape hatch):
FORCE_REFETCH=1 "$FETCH" fetch "$PROJECT_PATH" "$URL"
```

**Browser fallback (when `fetch` returns exit code 2 = blocked, or the page is JS-rendered):** a hard-WAF'd page won't yield to `curl`. The sequence is **check → capture → save**:

```bash
# 1. check the cache first — skip the browser entirely if already captured
"$FETCH" get "$PROJECT_PATH" "$URL" && exit 0
# 2. capture with the Chrome MCP (navigate + get_page_text) — uses the real browser session, passes the WAF
# 3. save the captured text into the cache so the next run reuses it instead of re-capturing:
printf '%s' "$CAPTURED_TEXT" | "$FETCH" put "$PROJECT_PATH" "$URL"
```

This is the documented, expected escape hatch, not a workaround.

## Step 1: Crawl the full site (cached + rate-limited)

```bash
FETCH="orchestration/lib/cached-fetch.sh"
# Polite recursive crawl into <project>/.reference/cache/_crawl/ — rate-limited,
# retries transient/WAF codes, warns + advises slow-down if still blocked.
"$FETCH" crawl "$PROJECT_PATH" "{URL}" 3
# If it reports WAF/rate-limit responses, re-run gentler:
#   RATE_DELAY=8 "$FETCH" crawl "$PROJECT_PATH" "{URL}" 3
# Failed URLs are written to <project>/.reference/cache/_crawl/_crawl-errors.txt

CACHE="$("$FETCH" cache-root "$PROJECT_PATH")"
echo "=== CRAWL RESULTS ==="
echo "Pages cached: $(find "$CACHE/_crawl" -name '*.html' 2>/dev/null | wc -l)"
echo "Failed URLs:  $(wc -l < "$CACHE/_crawl/_crawl-errors.txt" 2>/dev/null || echo 0)"
```

### Crawl error report (MANDATORY — present to user before continuing)

```bash
CRAWL_ERRORS="$(orchestration/lib/cached-fetch.sh cache-root "$PROJECT_PATH")/_crawl/_crawl-errors.txt"
if [ -s "$CRAWL_ERRORS" ]; then
  echo "WARNING: The following pages failed to download and CANNOT be migrated from the reference site:"
  cat "$CRAWL_ERRORS"
  echo ""
  echo "Save to workflow output for tracking:"
  mkdir -p workflow-output && cp "$CRAWL_ERRORS" workflow-output/crawl-errors.txt
else
  echo "All pages downloaded successfully."
fi
```

> If the failures are 403/429/5xx (not 404), that is a **WAF/rate-limit block, not missing content** — re-run the crawl with a higher `RATE_DELAY`, or capture those specific pages via the browser fallback, before declaring them un-migratable.

Present the error list to the user and agree on one of these options before continuing:

```
CRAWL COMPLETE

Pages OK:     N
Pages failed: M

Failed pages (cannot be analyzed automatically):
  - /fr-FR/les-exposants (500)
  - /fr-FR/medias (403)

Options:
  A) Skip these pages — mark as "manual migration required" in state.json
  B) Retry later when the reference site recovers
  C) Provide the HTML files manually (paste or file path)

Which option?
```

**Never silently skip failed pages.** A page that 500s on the reference site during crawl will result in a missing page or empty content in the Jahia migration — invisible until the visual diff.

For option A, record in `workflow-output/state.json`:
```bash
python3 - << 'EOF'
import json, os

state_path = 'workflow-output/state.json'
os.makedirs(os.path.dirname(state_path), exist_ok=True)
try:
    state = json.load(open(state_path))
except:
    state = {"steps": {}}

import subprocess
cache = subprocess.run(['orchestration/lib/cached-fetch.sh','cache-root',os.environ.get('PROJECT_PATH','.')],
                       capture_output=True, text=True).stdout.strip()
errpath = os.path.join(cache, '_crawl', '_crawl-errors.txt')
with open(errpath) as f:
    failed = [l.strip() for l in f if l.strip()]

state['crawlErrors'] = failed
state['crawlErrorAction'] = 'skipped-manual-required'

with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)

print(f"Recorded {len(failed)} pages as requiring manual migration.")
EOF
```

Then inventory every cached HTML file (`CRAWL_DIR` is the cache crawl dir from Step 1):

```bash
CRAWL_DIR="$(orchestration/lib/cached-fetch.sh cache-root "$PROJECT_PATH")/_crawl"
find "$CRAWL_DIR" -name "*.html" | sort > /tmp/page-list.txt
wc -l /tmp/page-list.txt
```

Report the page count to the user before continuing. If 0 pages were cached, the site is blocking the crawler (WAF) — slow down (`RATE_DELAY=8`) and/or fall back to Chrome MCP to capture each page into the cache dir.

---

## Step 2: Build the section corpus

For every page in `/tmp/page-list.txt`, extract all top-level structural blocks. A structural block is any of:
- `<section ...>` — any section tag
- `<article ...>` — any article tag
- `<header ...>`, `<footer ...>`, `<nav ...>`
- `<div class="...">` whose class string contains: `hero`, `banner`, `section`, `block`, `area`, `zone`, `wrapper`, `push`, `card`, `listing`, `slider`, `carousel`, `tabs`, `accordion`, `content-`, `-content`, `component`

For each block record:
- Source page path
- Top-level CSS class signature (the class attribute of the root element, verbatim)
- Inner child tag signature (e.g. `ul > li*N`, `div.card*4`, `article*3`) — what repeating children exist
- Whether it contains images, links, headings, richtext

Store this corpus as `/tmp/section-corpus.json`:

```json
[
  {
    "page": ".reference/cache/_crawl/fr-FR/index.html",
    "rootTag": "div",
    "classSignature": "component content hero-section",
    "childSignature": "none",
    "hasImage": true,
    "hasHeading": true,
    "hasRichtext": false,
    "hasRepeatingChildren": false,
    "childCount": 0,
    "htmlSnippet": "<div class=\"component content hero-section\">...</div>"
  }
]
```

---

## Step 3: Cluster by structural similarity

Group corpus entries by **class signature similarity**. Two blocks belong to the same cluster if:
- Their root CSS class strings share ≥2 significant tokens (ignore utility tokens like `col-*`, `container`, `row`, `component`, `content`)
- OR their child structure is identical (same tag pattern, same child count range)

For each cluster:
- Assign a **component name** (derived from the dominant CSS class)
- Count **frequency** — how many pages contain this pattern
- List **pages** where it appears
- Identify **variation axes** — what differs across instances: text only? image? modifier class? child count?

Minimum frequency threshold: a pattern that appears on only 1 page may still be a real component (e.g. a contact form unique to the contact page). Include it but flag `frequency: 1`.

---

## Step 4: Decide component type and views for each cluster

For each cluster, decide:

### 4a: Component type

| Pattern | Decision |
|---|---|
| Appears in page areas, no own URL | `jnt:content` + page area component |
| Has its own detail page (news, events, products) | `jmix:mainResource` content stored in `jnt:contentFolder` |
| Header or footer (appears on every page, wraps whole page) | `jnt:content` + `areaType: "absolute"` |
| Navigation menu | `jnt:content` + `areaType: "absolute"` — uses Jahia navigation API |
| Repeating list of same child type | Container `isContainer: true` + child type |

### 4b: Views — MANDATORY decision per component

Every component must have at least one view. Assign views based on how the component is used:

| Usage on the site | Views to create |
|---|---|
| Only appears inside a page area | `default` only |
| Appears as a card in a listing AND has a full detail page | `default` (card) + `fullPage` (detail page) |
| Appears in different visual sizes/layouts | `default` + named variant (e.g. `featured`, `compact`) |
| `jmix:mainResource` content | **Always** `default` + `fullPage` — no exceptions |

Document for each component:

```json
{
  "name": "NewsArticle",
  "nodeType": "ns:newsArticle",
  "needsMainResource": true,
  "views": [
    {
      "name": "default",
      "file": "default.server.tsx",
      "purpose": "Card/teaser shown in news listing grid",
      "htmlSource": "page: /news/index.html, class: .news-card"
    },
    {
      "name": "fullPage",
      "file": "fullPage.server.tsx",
      "purpose": "Full article detail page at /sites/.../contents/news/slug.html",
      "htmlSource": "page: /news/article-slug.html, class: .article-full"
    }
  ]
}
```

---

## Step 5: Extract canonical HTML fragments

For each component AND each of its views, extract the verbatim HTML fragment from the downloaded files.

Rules:
1. Open the source HTML file identified in the corpus entry
2. Locate the root element by its class signature using grep to find the exact line
3. Copy the **complete HTML block** — every element, every attribute, every nesting level
4. For containers (carousels, grids): copy wrapper + **one complete child item**
5. Replace ONLY dynamic text/URLs with `{placeholders}`: `<h1>Actual text</h1>` → `<h1>{heading}</h1>`
6. **NEVER** modify: CSS classes, `data-*`, `aria-*`, `role`, wrapper `<div>`s, `<noscript>`, `<source>`, inline `style`

**Self-check:** Run `grep -c "class=" SOURCE_FILE` vs count in your fragment. If yours has fewer class attributes, you simplified — re-extract.

For `fullPage` view: the source is the detail page HTML (e.g. `/news/article-slug.html`), not the listing page. Extract the full article layout from that page.

---

## Step 6: Extract content data

For every component instance across every page, extract all actual field values:

```json
{
  "componentType": "NewsArticle",
  "view": "default",
  "instanceName": "article-innovation-2024",
  "page": "/news/index.html",
  "order": 1,
  "contentArea": "main",
  "fields": {
    "title": "Actual article title",
    "summary": "<p>Actual summary text</p>",
    "publishDate": "2024-10-15",
    "image": "https://cdn.example.com/news/article.jpg",
    "detailPageUrl": "/news/article-innovation-2024"
  },
  "fullPageFields": {
    "bodyContent": "<p>Full article body HTML...</p>",
    "author": "Name Surname",
    "tags": ["innovation", "food-tech"]
  }
}
```

For `jmix:mainResource` components: always extract both `fields` (card data) and `fullPageFields` (detail page data). Navigate to the detail URL and extract its full content.

Extract ALL instances of every repeating component — never a subset.

---

## Step 7: Mandatory verification gate

Before saving results:

| Check | Requirement |
|---|---|
| Every cluster has ≥1 HTML fragment | Sourced from actual file, grep-verified line number |
| Every `jmix:mainResource` has both `default` and `fullPage` views | No exceptions |
| Every `fullPage` view has a fragment from the detail page HTML | Not invented from the listing page |
| Every `fullPageFields` has actual content | Not empty `{}` |
| Field names in content-data match manifest field definitions | No orphan fields |
| All repeating items fully extracted | Count in HTML = count in content-data |
| Every image URL recorded in asset-inventory | No image URLs in content-data missing from assets |

**HARD STOPS — do not write output files until all pass:**

```bash
# Verify every claimed CSS class exists in the cached HTML
CRAWL_DIR="$(orchestration/lib/cached-fetch.sh cache-root "$PROJECT_PATH")/_crawl"
for class in "hero-section" "news-card" "article-full"; do
  count=$(grep -rl "$class" "$CRAWL_DIR" | wc -l)
  echo "$class: found in $count files"
done
```

If count = 0 for any class: you invented it. Re-extract from the actual files.

---

## Step 8: Save outputs

Find project directory: `find . -name "definitions.cnd" -path "*/settings/*" | head -1` → grandparent.

```bash
mkdir -p $PROJECT_DIR/workflow-output
```

Save:
- `workflow-output/analysis.md` — component specs with HTML fragments per view, cluster stats
- `workflow-output/component-manifest.json` — structured list with fields, flags, and views
- `workflow-output/content-data.json` — all extracted content including fullPageFields
- `workflow-output/asset-inventory.json` — all images catalogued by component and page

---

## component-manifest.json structure

> **Namespace:** use the `namespace` / `mixNamespace` given in the step inputs for every `nodeType` (e.g. `usg:newsArticle`). Never invent a prefix. If inputs omit it, read it from `settings/definitions.cnd`. A manifest whose prefix disagrees with the scaffolded module breaks every downstream step.

```json
{
  "components": [
    {
      "name": "NewsArticle",
      "nodeType": "ns:newsArticle",
      "displayName": "News Article",
      "areaType": "page",
      "needsMainResource": true,
      "interactive": false,
      "isContainer": false,
      "childType": null,
      "clusterFrequency": 12,
      "clusterPages": ["/news/index.html", "/home.html", "..."],
      "views": [
        {
          "name": "default",
          "file": "default.server.tsx",
          "purpose": "Card in news listing grid",
          "htmlFragmentSource": ".reference/cache/_crawl/news/index.html:line 142"
        },
        {
          "name": "fullPage",
          "file": "fullPage.server.tsx",
          "purpose": "Full article detail page",
          "htmlFragmentSource": ".reference/cache/_crawl/news/article-slug.html:line 38"
        }
      ],
      "fields": [
        { "name": "title", "type": "string", "i18n": true, "mandatory": true },
        { "name": "summary", "type": "string, richtext", "i18n": true, "mandatory": false },
        { "name": "publishDate", "type": "date", "i18n": false, "mandatory": false },
        { "name": "image", "type": "weakreference, picker[type='image']", "mandatory": false },
        { "name": "bodyContent", "type": "string, richtext", "i18n": true, "mandatory": false }
      ]
    },
    {
      "name": "HeroSection",
      "nodeType": "ns:heroSection",
      "displayName": "Hero Section",
      "areaType": "page",
      "needsMainResource": false,
      "interactive": false,
      "isContainer": false,
      "childType": null,
      "clusterFrequency": 15,
      "clusterPages": ["every page"],
      "views": [
        {
          "name": "default",
          "file": "default.server.tsx",
          "purpose": "Full-width hero banner with background image and heading",
          "htmlFragmentSource": ".reference/cache/_crawl/fr-FR/index.html:line 88"
        }
      ],
      "fields": [
        { "name": "heading", "type": "string", "i18n": true, "mandatory": true },
        { "name": "subheading", "type": "string", "i18n": true, "mandatory": false },
        { "name": "backgroundImage", "type": "weakreference, picker[type='image']", "mandatory": false }
      ]
    }
  ]
}
```

**Flags:**
- `areaType: "absolute"` → header/footer/nav (placed via `<AbsoluteArea>` in Layout.tsx)
- `needsMainResource: true` → content type stored in `jnt:contentFolder`, has its own URL, MUST have both `default` and `fullPage` views
- `interactive: true` → needs a `.client.tsx` island
- `isContainer: true` → has child components via `+ * (childType)` in CND
- `clusterFrequency` → how many pages contain this pattern (higher = more likely truly reusable)

---

## Human validation gate (MANDATORY)

After saving all 4 output files, present this summary and **STOP. Do not proceed to step 2 or 3 until the user explicitly confirms.**

```
STEP 1 COMPLETE - VALIDATION REQUIRED

Pages crawled:           N  (from /tmp/page-list.txt)
Section corpus entries:  M  (total blocks extracted across all pages)
Clusters identified:     K  (distinct component candidates)
Components confirmed:    J  (after merging near-duplicates)

Per-component view assignment:
  - default view only:         X components  (page-area only, no own URL)
  - default + fullPage views:  Y components  (jmix:mainResource, has detail page)
  - default + named variant:   Z components  (e.g. featured, compact)

jmix:mainResource types:   Y  (each has fullPage HTML fragment sourced from detail page)

HTML fragments:  ALL sourced from .reference/cache/_crawl/ — grep line numbers verified
CSS classes:     ALL verified present in downloaded HTML files

Files written:
- workflow-output/analysis.md
- workflow-output/component-manifest.json
- workflow-output/content-data.json
- workflow-output/asset-inventory.json

CLUSTER SUMMARY:
  ns:heroSection      - 15 pages  - 1 view  (default)
  ns:newsArticle      - 12 pages  - 2 views (default card + fullPage detail)
  ns:pushCard         -  8 pages  - 1 view  (default)
  ns:eventCard        -  6 pages  - 2 views (default card + fullPage detail)
  ns:mainNav          - 15 pages  - 1 view  (absolute area)
  ...

Type VALIDATED to continue to step 2, or describe what to fix.
```
