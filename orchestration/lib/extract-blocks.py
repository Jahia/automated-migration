#!/usr/bin/env python3
"""extract-blocks.py — Deterministic, CMS-agnostic semantic block extraction.

Extracts SEMANTIC blocks from crawled HTML — the components a contributor
would manage individually in a CMS. Focus on CMS-level components, not
every nested <div>.

Usage:
  python3 orchestration/lib/extract-blocks.py <project>

Detection strategy (agnostic, works for any CMS):
  1. CMS-declared components: elements with "component" in class (Sitecore SXA, Drupal blocks, WP widgets)
  2. Structural regions: <header>, <footer>, <nav>, <main>, <section>, <article>
  3. Content aggregations: blocks with 3+ images OR 3+ links (lists, grids, carousels)
  4. Rich content blocks: blocks with heading + (image OR rich text >100 chars)

Output:
  <project>/workflow-output/html-blocks.json
"""
import json
import os
import re
import sys
import time
from html.parser import HTMLParser


class ComponentExtractor(HTMLParser):
    """Extract CMS-level components from HTML."""

    STRUCTURAL_TAGS = {'header', 'footer', 'nav', 'main', 'section', 'article', 'aside', 'form'}

    def __init__(self):
        super().__init__()
        self.blocks = []
        self.tag_stack = []
        self.depth = 0
        self.block_counter = 0

        # Content tracking per block
        self._text_buf = []
        self._images = []
        self._links = []
        self._headings = []
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

        # Strategy 1: CMS-declared component ("component" in class)
        if 'component' in classes:
            is_component = True
            component_reason = 'cms-component'

        # Strategy 2: Structural region
        elif tag in self.STRUCTURAL_TAGS:
            is_component = True
            component_reason = 'structural-region'

        # Strategy 3: Section/article/div with meaningful classes
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
            self.tag_stack.append({
                'tag': tag,
                'classes': classes,
                'depth': self.depth,
                'reason': component_reason,
                'text_buf': [],
                'images': [],
                'links': [],
                'headings': [],
            })

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
        # Check if we're closing a tracked component
        if self.tag_stack and self.tag_stack[-1]['tag'] == tag and self.tag_stack[-1]['depth'] == self.depth:
            item = self.tag_stack.pop()
            text = ' '.join(item['text_buf']).strip()
            text_len = len(text)
            images = item['images']
            links = item['links']
            headings = item['headings']

            # Determine if this block is worth keeping
            keep = False

            # Has CMS component marker
            if item['reason'] == 'cms-component':
                keep = True

            # Has structural region
            elif item['reason'] == 'structural-region':
                keep = text_len > 50 or images or headings

            # Has semantic class
            elif item['reason'] == 'semantic-class':
                keep = text_len > 30 or images or headings

            # Has multiple content items (list/grid pattern)
            if len(images) >= 3 or len(links) >= 5:
                keep = True

            # Has heading + content
            if headings and (text_len > 50 or images):
                keep = True

            if keep:
                self.block_counter += 1
                block_id = f"block_{self.block_counter:03d}"

                parent = self.tag_stack[-1] if self.tag_stack else None
                self.blocks.append({
                    'id': block_id,
                    'tag': item['tag'],
                    'classes': item['classes'],
                    'depth': item['depth'],
                    'detectionReason': item['reason'],
                    'parentTag': parent['tag'] if parent else None,
                    'parentClasses': parent['classes'][:3] if parent else [],
                    'textContent': text[:2000],
                    'textContentLength': text_len,
                    'imageCount': len(images),
                    'linkCount': len(links),
                    'headingCount': len(headings),
                    'hasImage': bool(images),
                    'hasLink': bool(links),
                    'hasHeading': bool(headings),
                    'imageUrls': images[:10],
                    'linkUrls': links[:20],
                    'headingTexts': headings[:5],
                })

        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return

        # Add text to all tracked components
        for item in self.tag_stack:
            item['text_buf'].append(text)

        # Track heading text
        if self._current_heading:
            for item in self.tag_stack:
                item['headings'].append(text[:200])
            self._current_heading = None

    def get_result(self, page_slug, page_url):
        return {
            'slug': page_slug,
            'url': page_url,
            'blocks': self.blocks,
            'totalBlocks': len(self.blocks),
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
        by_reason = {}
        for b in blocks:
            r = b.get('detectionReason', '?')
            by_reason[r] = by_reason.get(r, 0) + 1
        reason_str = ', '.join(f'{k}={v}' for k, v in by_reason.items())
        print(f"  {page['slug']:30s} components={len(blocks):3d}  ({reason_str})")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
