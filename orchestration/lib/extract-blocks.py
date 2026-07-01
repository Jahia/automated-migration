#!/usr/bin/env python3
"""extract-blocks.py — Deterministic, CMS-agnostic semantic block extraction.

Extracts SEMANTIC blocks with parent-child hierarchy from crawled HTML.
Handles nested components (containers with child slots).

Usage:
  python3 orchestration/lib/extract-blocks.py <project>

Detection strategies (agnostic):
  1. CMS-declared: "component" in class (Sitecore SXA, Drupal blocks, WP widgets)
  2. Structural: <header>, <footer>, <nav>, <main>, <section>, <article>
  3. Semantic classes: hero, banner, carousel, grid, listing, faq, etc.
  4. Content aggregation: 3+ images or 5+ links (lists, carousels)

Output:
  <project>/workflow-output/html-blocks.json
"""
import json
import os
import sys
import time
from html.parser import HTMLParser


class ComponentExtractor(HTMLParser):
    """Extract CMS-level components with parent-child hierarchy."""

    STRUCTURAL_TAGS = {'header', 'footer', 'nav', 'main', 'section', 'article', 'aside', 'form'}

    def __init__(self):
        super().__init__()
        self.blocks = []
        self.tag_stack = []  # stack of active component dicts
        self.depth = 0
        self.block_counter = 0

        # Content tracking
        self._current_heading = None

        # Global structure
        self.has_header = False
        self.has_footer = False
        self.has_nav = False
        self.has_main = False

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        attrs_d = dict(attrs)
        classes = attrs_d.get('class', '').split()
        class_str = attrs_d.get('class', '')

        if tag == 'header':
            self.has_header = True
        elif tag == 'footer':
            self.has_footer = True
        elif tag == 'nav':
            self.has_nav = True
        elif tag == 'main':
            self.has_main = True

        # Check if this is a component we should track
        is_component = False
        component_reason = None

        if 'component' in classes:
            is_component = True
            component_reason = 'cms-component'
        elif tag in self.STRUCTURAL_TAGS:
            is_component = True
            component_reason = 'structural-region'
        elif tag in ('section', 'article') or (tag == 'div' and any(
            k in class_str.lower() for k in [
                'hero', 'banner', 'slider', 'carousel', 'gallery', 'grid',
                'listing', 'cards', 'push', 'teaser', 'widget', 'block',
                'module', 'feature', 'testimonial', 'faq', 'accordion', 'tabs',
                'map', 'video', 'social', 'newsletter', 'search', 'breadcrumb',
                'cta', 'call-to-action', 'pricing', 'team', 'portfolio',
            ]
        )):
            is_component = True
            component_reason = 'semantic-class'

        if is_component:
            self.block_counter += 1
            block_id = f"block_{self.block_counter:03d}"

            parent_id = self.tag_stack[-1]['id'] if self.tag_stack else None

            block = {
                'id': block_id,
                'tag': tag,
                'classes': classes,
                'depth': self.depth,
                'detectionReason': component_reason,
                'parentId': parent_id,
                'childIds': [],
                'text_buf': [],
                'images': [],
                'links': [],
                'headings': [],
            }
            self.blocks.append(block)
            self.tag_stack.append(block)

        # Track content
        if tag == 'img':
            src = attrs_d.get('src', '') or attrs_d.get('data-src', '') or attrs_d.get('data-lazy-src', '')
            if src and not src.startswith('data:'):
                for item in reversed(self.tag_stack):
                    item['images'].append(src)
                    break
        elif tag == 'a':
            href = attrs_d.get('href', '')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                for item in reversed(self.tag_stack):
                    item['links'].append(href)
                    break
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._current_heading = tag

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1]['tag'] == tag and self.tag_stack[-1]['depth'] == self.depth:
            item = self.tag_stack.pop()
            # Add this block as child of parent
            if self.tag_stack:
                self.tag_stack[-1]['childIds'].append(item['id'])

        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return

        for item in self.tag_stack:
            item['text_buf'].append(text)

        if self._current_heading:
            for item in self.tag_stack:
                item['headings'].append(text[:200])
            self._current_heading = None

    def get_result(self, page_slug, page_url):
        # Clean up blocks: remove internal buffers, compute derived fields
        clean_blocks = []
        for b in self.blocks:
            text = ' '.join(b['text_buf']).strip()
            clean_blocks.append({
                'id': b['id'],
                'tag': b['tag'],
                'classes': b['classes'],
                'depth': b['depth'],
                'detectionReason': b['detectionReason'],
                'parentId': b['parentId'],
                'childIds': b['childIds'],
                'childCount': len(b['childIds']),
                'isContainer': len(b['childIds']) > 0,
                'textContent': text[:2000],
                'textContentLength': len(text),
                'imageCount': len(b['images']),
                'linkCount': len(b['links']),
                'headingCount': len(b['headings']),
                'hasImage': bool(b['images']),
                'hasLink': bool(b['links']),
                'hasHeading': bool(b['headings']),
                'imageUrls': b['images'][:10],
                'linkUrls': b['links'][:20],
                'headingTexts': b['headings'][:5],
            })

        # Build hierarchy summary
        roots = [b for b in clean_blocks if b['parentId'] is None]
        containers = [b for b in clean_blocks if b['isContainer']]

        return {
            'slug': page_slug,
            'url': page_url,
            'blocks': clean_blocks,
            'totalBlocks': len(clean_blocks),
            'rootBlocks': len(roots),
            'containerBlocks': len(containers),
            'globalStructure': {
                'hasHeader': self.has_header,
                'hasFooter': self.has_footer,
                'hasNav': self.has_nav,
                'hasMain': self.has_main,
            }
        }


def extract_blocks_from_page(html_path, page_slug, page_url):
    try:
        with open(html_path, 'r', errors='replace') as f:
            html = f.read()
    except Exception:
        return None

    parser = ComponentExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    return parser.get_result(page_slug, page_url)


def main():
    if len(sys.argv) < 2:
        print("Usage: extract-blocks.py <project>", file=sys.stderr)
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

    all_pages = []
    total_blocks = 0
    for page in pages:
        html_path = os.path.join(proj, page.get("cachedAt", ""))
        if not os.path.isfile(html_path):
            print(f"  WARNING: cached file not found for {page['slug']}", file=sys.stderr)
            continue

        result = extract_blocks_from_page(html_path, page["slug"], page["url"])
        if result:
            all_pages.append(result)
            total_blocks += len(result["blocks"])

    output = {
        "extractedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totalPages": len(all_pages),
        "totalBlocks": total_blocks,
        "pages": all_pages,
    }
    out_path = f"{proj}/workflow-output/html-blocks.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"=== COMPONENT EXTRACTION ===")
    print(f"Pages: {len(all_pages)}")
    print(f"Total components: {total_blocks}")
    print()
    for page in all_pages:
        blocks = page["blocks"]
        containers = [b for b in blocks if b['isContainer']]
        leaves = [b for b in blocks if not b['isContainer']]
        print(f"  {page['slug']:30s} total={len(blocks):3d}  containers={len(containers):2d}  leaves={len(leaves):2d}")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
