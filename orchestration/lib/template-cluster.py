#!/usr/bin/env python3
"""template-cluster.py — Group pages by shared template structure.

Analyzes the HTML skeleton of each crawled page (header, footer, nav, main
content regions) and clusters pages that share the same layout template.

Usage:
  python3 orchestration/lib/template-cluster.py <project>

Input:
  <project>/workflow-output/page-inventory.json
  <project>/.reference/cache/_crawl/  (HTML files)

Output:
  <project>/workflow-output/template-clusters.json
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from html.parser import HTMLParser


class StructureExtractor(HTMLParser):
    """Extract the structural skeleton of a page."""

    def __init__(self):
        super().__init__()
        self.structure = []
        self.depth = 0
        self.in_header = False
        self.in_footer = False
        self.in_nav = False
        self.components = []
        self.current_tag = None
        self.current_class = ""

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        cls = attrs_d.get("class", "")
        self.depth += 1

        if tag == "header":
            self.in_header = True
            self.structure.append("HEADER")
        elif tag == "footer":
            self.in_footer = True
            self.structure.append("FOOTER")
        elif tag == "nav":
            self.in_nav = True

        # Track components (Sitecore SXA pattern)
        if "component" in cls:
            comp_type = self._extract_component_type(cls)
            region = "header" if self.in_header else "footer" if self.in_footer else "nav" if self.in_nav else "page"
            self.components.append({
                "type": comp_type,
                "class": cls[:100],
                "region": region,
                "depth": self.depth,
            })

        # Track main content structure
        if tag in ("section", "article", "main") or (tag == "div" and any(k in cls for k in ["hero", "banner", "content", "section", "block", "grid", "listing"])):
            section_type = self._classify_section(cls, tag)
            if section_type:
                self.structure.append(section_type)

        self.current_tag = tag
        self.current_class = cls

    def handle_endtag(self, tag):
        if tag == "header":
            self.in_header = False
        elif tag == "footer":
            self.in_footer = False
        elif tag == "nav":
            self.in_nav = False
        self.depth = max(0, self.depth - 1)

    def _extract_component_type(self, cls):
        """Extract component type from SXA class pattern."""
        # SXA: "component <type>" or "component <type> <variant>"
        parts = cls.split()
        if "component" in parts:
            idx = parts.index("component")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "unknown"

    def _classify_section(self, cls, tag):
        """Classify a section by its CSS classes."""
        cls_lower = cls.lower()
        if any(k in cls_lower for k in ["hero", "banner"]):
            return "HERO"
        if any(k in cls_lower for k in ["grid", "listing", "cards", "push"]):
            return "GRID"
        if any(k in cls_lower for k in ["accordion", "tabs", "faq"]):
            return "ACCORDION"
        if any(k in cls_lower for k in ["slider", "carousel"]):
            return "CAROUSEL"
        if tag == "section":
            return "SECTION"
        # Only classify as CONTENT if it's a meaningful content block
        if tag in ("article", "main") or (tag == "div" and any(k in cls_lower for k in ["content-block", "richtext", "rich-text", "text-block"])):
            return "CONTENT"
        return None


def extract_structure(html_path):
    """Extract structural signature from an HTML file."""
    try:
        with open(html_path, "r", errors="replace") as f:
            html = f.read()
    except Exception:
        return None

    parser = StructureExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    return {
        "structure": parser.structure,
        "components": parser.components,
    }


def compute_signature(structure):
    """Compute a normalized signature for clustering."""
    # Use the ordered list of section types as the signature
    sig_parts = []
    for s in structure["structure"]:
        if s in ("HEADER", "FOOTER"):
            continue  # These are cross-cutting, not template-specific
        sig_parts.append(s)
    return "|".join(sig_parts) if sig_parts else "EMPTY"


def extract_cross_cutting(all_structures):
    """Identify components that appear on ALL pages (header, footer, nav).

    Uses multiple strategies:
    1. Components with region=header/footer/nav that appear on all pages
    2. Known cross-cutting component names (top-bar, main-navigation, footer)
    3. HTML <header>/<footer> tags (via structure)
    """
    if not all_structures:
        return {}

    total_pages = len(all_structures)

    # Strategy 1: Count component types across all pages by region
    component_counts = Counter()
    component_regions = defaultdict(set)
    header_footer_tags = Counter()

    for page, struct in all_structures.items():
        seen_types = set()
        for comp in struct.get("components", []):
            ctype = comp["type"]
            if ctype not in seen_types:
                component_counts[ctype] += 1
                seen_types.add(ctype)
            component_regions[ctype].add(comp["region"])

        # Strategy 2: Check for HEADER/FOOTER in structure
        for s in struct.get("structure", []):
            if s == "HEADER":
                header_footer_tags["header"] += 1
            elif s == "FOOTER":
                header_footer_tags["footer"] += 1

    cross_cutting = {}

    # Known cross-cutting component names (Sitecore SXA patterns)
    known_cc = {
        "top-bar": "header",
        "top-navbar": "header",
        "main-navigation": "header",
        "main-nav": "header",
        "navigation": "header",
        "header": "header",
        "footer": "footer",
        "site-footer": "footer",
        "footer-section": "footer",
    }

    # Strategy 3: Add known cross-cutting components if they appear on >= 50% of pages
    # (some pages might not have them detected due to HTML structure)
    for ctype, region in known_cc.items():
        if component_counts.get(ctype, 0) >= max(1, total_pages * 0.5):
            cross_cutting[ctype] = {
                "pages": "all",
                "componentSignature": f"component {ctype}",
                "region": region,
            }

    # Strategy 4: Add header/footer if <header>/<footer> tags found on all pages
    if header_footer_tags.get("header", 0) >= max(1, total_pages * 0.5):
        if "header" not in cross_cutting:
            cross_cutting["header"] = {
                "pages": "all",
                "componentSignature": "<header> tag",
                "region": "header",
            }

    if header_footer_tags.get("footer", 0) >= max(1, total_pages * 0.5):
        if "footer" not in cross_cutting:
            cross_cutting["footer"] = {
                "pages": "all",
                "componentSignature": "<footer> tag",
                "region": "footer",
            }

    return cross_cutting


def main():
    if len(sys.argv) < 2:
        print("Usage: template-cluster.py <project>", file=sys.stderr)
        sys.exit(1)

    proj = sys.argv[1]
    inv_path = f"{proj}/workflow-output/page-inventory.json"

    if not os.path.isfile(inv_path):
        print(f"FAIL: {inv_path} not found (run crawl first)", file=sys.stderr)
        sys.exit(1)

    inventory = json.load(open(inv_path))
    pages = inventory.get("pages", [])

    if not pages:
        print("FAIL: 0 pages in inventory", file=sys.stderr)
        sys.exit(1)

    # Extract structure from each page
    all_structures = {}
    for page in pages:
        html_path = os.path.join(proj, page.get("cachedAt", ""))
        if not os.path.isfile(html_path):
            print(f"  WARNING: cached file not found for {page['slug']}: {html_path}", file=sys.stderr)
            continue

        struct = extract_structure(html_path)
        if struct:
            all_structures[page["slug"]] = struct

    if not all_structures:
        print("FAIL: could not extract structure from any page", file=sys.stderr)
        sys.exit(1)

    # Cluster by signature
    clusters = defaultdict(list)
    for slug, struct in all_structures.items():
        sig = compute_signature(struct)
        clusters[sig].append(slug)

    # Build cluster objects
    cluster_list = []
    for sig, slugs in sorted(clusters.items(), key=lambda x: -len(x[1])):
        # Analyze the first page in the cluster for details
        first_slug = slugs[0]
        first_struct = all_structures[first_slug]
        components = [c for c in first_struct["components"] if c["region"] == "page"]

        cluster_list.append({
            "clusterId": f"template-{len(cluster_list)+1}",
            "description": f"Template with {sig.replace('|', ' + ')} structure",
            "pages": slugs,
            "structuralSignature": sig,
            "sharedRegions": ["header", "footer"],
            "mainContentPattern": sig,
            "componentTypes": list(set(c["type"] for c in components)),
        })

    # Identify cross-cutting components
    cross_cutting = extract_cross_cutting(all_structures)

    # Find unclustered pages (should be none if all pages were processed)
    all_slugs = {p["slug"] for p in pages}
    clustered_slugs = set()
    for c in cluster_list:
        clustered_slugs.update(c["pages"])
    unclustered = sorted(all_slugs - clustered_slugs)

    # Write output
    output = {
        "clusters": cluster_list,
        "crossCutting": cross_cutting,
        "unclustered": unclustered,
    }
    out_path = f"{proj}/workflow-output/template-clusters.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    # Report
    print(f"=== TEMPLATE CLUSTERS ===")
    print(f"Pages analyzed: {len(all_structures)}")
    print(f"Clusters: {len(cluster_list)}")
    for c in cluster_list:
        print(f"  {c['clusterId']}: {len(c['pages'])} pages — {c['description']}")
        print(f"    Pages: {', '.join(c['pages'])}")
        print(f"    Components: {', '.join(c['componentTypes'][:5])}")
    print(f"Cross-cutting: {', '.join(cross_cutting.keys())}")
    if unclustered:
        print(f"Unclustered: {unclustered}")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
