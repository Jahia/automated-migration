#!/usr/bin/env python3
"""component-discover.py — Discover reusable components from crawled pages.

Walks all structural blocks across all pages, clusters by data shape
(same fields = same type, even if CSS differs), and identifies
cross-cutting vs page-specific components.

Usage:
  python3 orchestration/lib/component-discover.py <project>

Input:
  <project>/workflow-output/page-inventory.json
  <project>/workflow-output/template-clusters.json
  <project>/.reference/cache/_crawl/  (HTML files)

Output:
  <project>/workflow-output/component-candidates.json
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from html.parser import HTMLParser


class ComponentExtractor(HTMLParser):
    """Extract component blocks from Sitecore SXA or generic HTML."""

    def __init__(self, page_slug):
        super().__init__()
        self.page_slug = page_slug
        self.components = []
        self.depth = 0
        self.in_component = False
        self.current_component = None
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        cls = attrs_d.get("class", "")
        self.depth += 1
        self.tag_stack.append(tag)

        # Sitecore SXA: "component <type>" pattern
        if "component" in cls.split():
            comp_type = self._extract_component_type(cls)
            if comp_type and comp_type != "unknown":
                self.in_component = True
                self.current_component = {
                    "type": comp_type,
                    "class": cls[:150],
                    "page": self.page_slug,
                    "depth": self.depth,
                    "fields": self._extract_fields(cls),
                    "hasImage": False,
                    "hasLink": False,
                    "hasHeading": False,
                    "hasText": False,
                    "children": [],
                }
                self.components.append(self.current_component)

        # Track content within components
        if self.current_component:
            if tag == "img":
                self.current_component["hasImage"] = True
                self.current_component["fields"].append("image")
            elif tag == "a":
                self.current_component["hasLink"] = True
                self.current_component["fields"].append("link")
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.current_component["hasHeading"] = True
                self.current_component["fields"].append("heading")
            elif tag in ("p", "span", "div") and "text" in cls.lower():
                self.current_component["hasText"] = True
                self.current_component["fields"].append("text")

    def handle_endtag(self, tag):
        if self.current_component and self.depth <= self.current_component["depth"]:
            self.in_component = False
            self.current_component = None
        self.depth = max(0, self.depth - 1)
        if self.tag_stack:
            self.tag_stack.pop()

    def handle_data(self, data):
        if self.current_component:
            text = data.strip()
            if text and len(text) > 10:
                self.current_component["hasText"] = True

    def _extract_component_type(self, cls):
        """Extract component type from SXA class pattern."""
        parts = cls.split()
        if "component" in parts:
            idx = parts.index("component")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "unknown"

    def _extract_fields(self, cls):
        """Extract field names from SXA field-* classes."""
        fields = []
        for part in cls.split():
            if part.startswith("field-"):
                fields.append(part[6:])  # Remove "field-" prefix
        return fields


def extract_components_from_page(html_path, page_slug):
    """Extract components from a single page."""
    try:
        with open(html_path, "r", errors="replace") as f:
            html = f.read()
    except Exception:
        return []

    parser = ComponentExtractor(page_slug)
    try:
        parser.feed(html)
    except Exception:
        pass

    return parser.components


def compute_data_shape(component):
    """Compute a normalized data shape for clustering."""
    # Sort and deduplicate fields
    fields = sorted(set(component.get("fields", [])))
    # Add boolean flags (always include these as they define the shape)
    flags = []
    if component.get("hasImage"):
        flags.append("image")
    if component.get("hasLink"):
        flags.append("link")
    if component.get("hasHeading"):
        flags.append("heading")
    if component.get("hasText"):
        flags.append("text")
    # Combine fields and flags, remove duplicates
    all_shape = sorted(set(fields + flags))
    return ",".join(all_shape) if all_shape else "structural"


def is_main_resource_candidate(comp_type, pages):
    """Heuristic: is this component a mainResource (has its own URL)?"""
    # News articles, events, products typically have:
    # - their own page/URL
    # - a detail view
    # - appear in listings
    main_resource_hints = ["article", "news", "event", "product", "press", "blog", "post"]
    return any(hint in comp_type.lower() for hint in main_resource_hints)


def main():
    if len(sys.argv) < 2:
        print("Usage: component-discover.py <project>", file=sys.stderr)
        sys.exit(1)

    proj = sys.argv[1]
    inv_path = f"{proj}/workflow-output/page-inventory.json"
    cluster_path = f"{proj}/workflow-output/template-clusters.json"

    if not os.path.isfile(inv_path):
        print(f"FAIL: {inv_path} not found (run crawl first)", file=sys.stderr)
        sys.exit(1)

    inventory = json.load(open(inv_path))
    pages = inventory.get("pages", [])

    # Load clusters for cross-cutting detection
    cross_cutting_types = set()
    if os.path.isfile(cluster_path):
        clusters = json.load(open(cluster_path))
        for cc in clusters.get("crossCutting", {}).keys():
            cross_cutting_types.add(cc)

    # Extract components from all pages
    all_components = []
    for page in pages:
        html_path = os.path.join(proj, page.get("cachedAt", ""))
        if not os.path.isfile(html_path):
            continue
        comps = extract_components_from_page(html_path, page["slug"])
        all_components.extend(comps)

    if not all_components:
        print("FAIL: 0 components found across all pages", file=sys.stderr)
        sys.exit(1)

    # Group by component type
    type_groups = defaultdict(list)
    for comp in all_components:
        type_groups[comp["type"]].append(comp)

    # Build candidates
    candidates = []
    for comp_type, instances in sorted(type_groups.items(), key=lambda x: -len(x[1])):
        # Compute data shape from first instance
        first = instances[0]
        data_shape = compute_data_shape(first)

        # Collect all unique fields across instances
        all_fields = set()
        for inst in instances:
            all_fields.update(inst.get("fields", []))
            # Add boolean flags as fields
            if inst.get("hasImage"):
                all_fields.add("image")
            if inst.get("hasLink"):
                all_fields.add("link")
            if inst.get("hasHeading"):
                all_fields.add("heading")
            if inst.get("hasText"):
                all_fields.add("text")

        # Determine if cross-cutting
        pages_with = set(inst["page"] for inst in instances)
        is_cross_cutting = comp_type in cross_cutting_types

        # Determine if mainResource
        is_main_res = is_main_resource_candidate(comp_type, pages_with)

        candidates.append({
            "candidateId": comp_type,
            "role": f"Component: {comp_type}",
            "frequency": len(instances),
            "pages": sorted(pages_with),
            "dataShape": sorted(all_fields),
            "cssSignature": first.get("class", "")[:100],
            "isCrossCutting": is_cross_cutting,
            "isMainResource": is_main_res,
            "hasImage": any(inst.get("hasImage") for inst in instances),
            "hasLink": any(inst.get("hasLink") for inst in instances),
            "hasHeading": any(inst.get("hasHeading") for inst in instances),
            "hasText": any(inst.get("hasText") for inst in instances),
        })

    # Write output
    output = {
        "discoveredAt": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "totalCandidates": len(candidates),
        "crossCuttingCount": sum(1 for c in candidates if c["isCrossCutting"]),
        "mainResourceCount": sum(1 for c in candidates if c["isMainResource"]),
        "components": candidates,
    }
    out_path = f"{proj}/workflow-output/component-candidates.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    # Report
    print(f"=== COMPONENT DISCOVERY ===")
    print(f"Pages analyzed: {len(pages)}")
    print(f"Total component instances: {len(all_components)}")
    print(f"Unique component types: {len(candidates)}")
    print(f"Cross-cutting: {sum(1 for c in candidates if c['isCrossCutting'])}")
    print(f"MainResource candidates: {sum(1 for c in candidates if c['isMainResource'])}")
    print()
    for c in candidates[:15]:
        cc = " [CC]" if c["isCrossCutting"] else ""
        mr = " [MR]" if c["isMainResource"] else ""
        print(f"  {c['candidateId']:30s} freq={c['frequency']:3d}  pages={len(c['pages'])}  shape={','.join(c['dataShape'][:5]):30s}{cc}{mr}")
    if len(candidates) > 15:
        print(f"  ... and {len(candidates) - 15} more")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
