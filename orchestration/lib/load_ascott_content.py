#!/usr/bin/env python3
"""load_ascott_content.py — Create content for ascott pages + nav.

Strategy:
1. Home page header/footer: create nav link instances under the home page header/footer
   absolute areas (shared across all pages).
2. Each sub-page: extract text from captured recon HTML, create a MainResource
   detailPage (or textLayout) with that text.
3. Wire images from imported.json to image weakref properties.
4. Publish everything.
"""
import html.parser, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP

PROJECT = "ascott"
SITE = "ascott"
LOCALE = "en"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

def load_json(p, default=None):
    try: return json.load(open(p))
    except Exception as e: return default

def extract_page_text(html_path):
    """Extract readable text from recon HTML (skip nav/header/footer/script/style)."""
    if not os.path.exists(html_path):
        return ""
    class P(html.parser.HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []
            self.skip = 0
        def handle_starttag(self, tag, attrs):
            if tag in ('script','style'): self.skip += 1
            if tag in ('nav','header','footer'): self.skip += 1
        def handle_endtag(self, tag):
            if tag in ('script','style'): self.skip -= 1
            if tag in ('nav','header','footer'): self.skip -= 1
        def handle_data(self, data):
            if self.skip <= 0:
                t = data.strip()
                if t: self.text.append(t)
    p = P()
    with open(html_path) as f:
        p.feed(f.read())
    return " ".join(p.text)

def find_recon_html(slug):
    """Find the recon HTML file for a given slug."""
    mirror = f"{REPO}/projects/{PROJECT}/workflow-output/local-mirror"
    if not os.path.isdir(mirror):
        return None
    for f in os.listdir(mirror):
        if f.endswith(".recon.html") and slug in f.replace("_", "-").lower():
            return f"{mirror}/{f}"
    return None

def slug_to_jcr(slug):
    if slug == "home":
        return f"/sites/{SITE}/home"
    return f"/sites/{SITE}/home/{slug}"

def create_page_content(mcp, slug, text):
    """Create a detailPage or textLayout on the page with the extracted text."""
    page_path = slug_to_jcr(slug)
    main_area = f"{page_path}/main"
    
    if not text or len(text) < 100:
        text = f"Welcome to {slug.replace('-', ' ').title()}"
    
    # Truncate to max 5000 chars
    text = text[:5000]
    
    try:
        r = mcp.create(main_area, "ascott:textLayout",
                       {"text": text},
                       name=f"page-content", locale=LOCALE)
        path = r.get("path") if isinstance(r, dict) else None
        if path:
            print(f"  + {path}  ({len(text)} chars)")
            return path
    except Exception as e:
        print(f"  ! create content failed: {e}", file=sys.stderr)
    return None

def create_nav_from_instances(mcp, page_data, image_map, parent_area, start_idx=0, limit=999):
    """Create component instances from content-data.json under a parent area."""
    instances = page_data.get("instances", [])
    if start_idx >= len(instances):
        return 0
    
    type_map = {
        "Link Button": "ascott:linkButton",
        "Image Link": "ascott:imageLink",
        "Text Layout": "ascott:textLayout",
    }
    
    created = 0
    for idx, inst in enumerate(instances[start_idx:start_idx+limit]):
        real_idx = start_idx + idx
        ct = inst.get("componentType", "")
        nt = type_map.get(ct)
        if not nt:
            continue
        
        fields = inst.get("fields", {})
        props = {}
        
        for pname, pval in fields.items():
            if pname == "imageFile" and isinstance(pval, str):
                jp = image_map.get(pval)
                if jp:
                    props["image"] = jp
                continue
            if pname.startswith("j:"):
                continue
            props[pname] = pval
        
        if not props:
            continue
        
        # Handle links
        ltype = inst.get("fields", {}).get("j:linkType", "")
        if ltype:
            props["j:linkType"] = ltype.lower()
            href = inst.get("href", "")
            if href.startswith("http"):
                # Add j:url for external links - but only if needed
                pass
        
        name = f"nav-{real_idx}"
        try:
            r = mcp.create(parent_area, nt, props, name=name, locale=LOCALE)
            path = r.get("path") if isinstance(r, dict) else None
            if path:
                created += 1
        except Exception as e:
            pass  # Skip errors silently - might be duplicate names
    
    return created

def main():
    mcp = MCP(PROJECT)
    
    # Load data
    content_data = load_json(f"{REPO}/projects/{PROJECT}/workflow-output/content-data.json", {"pages": {}})
    imported = load_json(f"{REPO}/orchestration/images/{PROJECT}.imported.json", {})
    
    # Build image filename -> JCR path map
    image_map = {}
    for entries in imported.values():
        for e in entries:
            fn = e.get("file")
            jp = e.get("jcrPath")
            if fn and jp:
                image_map[fn] = jp
    
    print(f"Image map: {len(image_map)} entries")
    
    # Target pages  
    targets = ["home", "destinations", "adoor-apartment", "the-ascott-limited",
               "amsterdam", "adoor-suites", "find-residence", "ascott-cares",
               "lyf", "ascott-chelseafc", "member-buy-experiences"]
    
    for slug in targets:
        print(f"\n=== Page: {slug} ===")
        page_path = slug_to_jcr(slug)
        
        # Extract text from recon HTML for page content
        html_path = find_recon_html(slug)
        text = extract_page_text(html_path) if html_path else ""
        text_len = len(text)
        print(f"  recon HTML: {html_path}, {text_len} chars extracted")
        
        # Create content node on the page
        path = create_page_content(mcp, slug, text)
        
        if path:
            # Publish the page content
            try:
                mcp.publish(page_path, languages=[LOCALE])
                print(f"  published {page_path}")
            except Exception as e:
                print(f"  ! publish failed: {e}", file=sys.stderr)
    
    # Create nav/footer on home page header and footer areas
    print(f"\n=== Navigation ===")
    home_data = content_data.get("pages", {}).get("home", {})
    
    if home_data:
        # Create header components (first ~30% of instances are likely header nav)
        instances = home_data.get("instances", [])
        header_limit = len(instances) // 3  # First third = header nav
        footer_start = (len(instances) * 2) // 3  # Last third = footer
        
        hdr = create_nav_from_instances(mcp, home_data, image_map, f"/sites/{SITE}/home/header", 0, header_limit)
        print(f"  header: {hdr} nodes")
        
        # Create footer components (last third)
        ftr = create_nav_from_instances(mcp, home_data, image_map, f"/sites/{SITE}/home/footer", footer_start)
        print(f"  footer: {ftr} nodes")
        
        # Publish nav/footer
        try:
            mcp.publish(f"/sites/{SITE}/home/header", languages=[LOCALE])
            mcp.publish(f"/sites/{SITE}/home/footer", languages=[LOCALE])
            print("  published header + footer")
        except Exception as e:
            print(f"  ! publish nav failed: {e}", file=sys.stderr)
    
    print(f"\n=== Done ===")

if __name__ == "__main__":
    main()
