#!/usr/bin/env python3
"""extract-blocks.py — Deterministic, CMS-agnostic block extraction.

Extracts ALL structural blocks from crawled HTML with rich context for the LLM.
NO semantic decisions — pure data extraction. The LLM decides what's a component,
what's a template, what's cross-cutting.

Usage:
  python3 orchestration/lib/extract-blocks.py <project>

Output:
  <project>/workflow-output/html-blocks.json
"""
import json
import os
import re
import sys
import time
from html.parser import HTMLParser


class BlockExtractor(HTMLParser):
    """Extract all structural blocks from HTML with rich context."""

    # Tags that represent structural blocks
    BLOCK_TAGS = {
        'div', 'section', 'article', 'aside', 'nav', 'header', 'footer',
        'main', 'form', 'table', 'ul', 'ol', 'figure', 'details', 'dialog',
        'fieldset', 'blockquote', 'dl',
    }

    def __init__(self):
        super().__init__()
        self.blocks = []
        self.tag_stack = []  # (tag, classes, depth, block_id)
        self.depth = 0
        self.block_counter = 0
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

        if tag == 'header':
            self.has_header = True
        elif tag == 'footer':
            self.has_footer = True
        elif tag == 'nav':
            self.has_nav = True
        elif tag == 'main':
            self.has_main = True

        if tag in self.BLOCK_TAGS:
            self.block_counter += 1
            block_id = f"block_{self.block_counter:03d}"

            parent_id = self.tag_stack[-1][3] if self.tag_stack else None

            block = {
                'id': block_id,
                'tag': tag,
                'classes': classes,
                'depth': self.depth,
                'parentId': parent_id,
                'childIds': [],
                'text_buf': [],
                'images': [],
                'links': [],
                'headings': [],
                'heading_tag': None,
            }
            self.blocks.append(block)
            self.tag_stack.append((tag, classes, self.depth, block_id))

        # Track content
        if tag == 'img':
            src = attrs_d.get('src', '') or attrs_d.get('data-src', '') or attrs_d.get('data-lazy-src', '')
            if src and not src.startswith('data:'):
                for item in reversed(self.blocks):
                    if item['id'] == self.tag_stack[-1][3] if self.tag_stack else False:
                        item['images'].append(src)
                        break
        elif tag == 'a':
            href = attrs_d.get('href', '')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                for item in reversed(self.blocks):
                    if item['id'] == self.tag_stack[-1][3] if self.tag_stack else False:
                        item['links'].append(href)
                        break
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._current_heading = tag

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1][0] == tag and self.tag_stack[-1][2] == self.depth:
            popped = self.tag_stack.pop()
            block_id = popped[3]
            # Add this block as child of parent
            if self.tag_stack:
                parent_id = self.tag_stack[-1][3]
                for b in self.blocks:
                    if b['id'] == parent_id:
                        b['childIds'].append(block_id)
                        break

        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return

        # Add text to current block
        if self.tag_stack:
            current_id = self.tag_stack[-1][3]
            for b in self.blocks:
                if b['id'] == current_id:
                    b['text_buf'].append(text)
                    break

        # Track heading text
        if self._current_heading:
            if self.tag_stack:
                current_id = self.tag_stack[-1][3]
                for b in self.blocks:
                    if b['id'] == current_id:
                        b['headings'].append(text[:200])
                        b['heading_tag'] = self._current_heading
                        break
            self._current_heading = None

    def get_result(self, page_slug, page_url):
        # Build block map for sibling lookup
        block_map = {b['id']: b for b in self.blocks}

        # Filter: keep meaningful blocks, skip empty layout wrappers
        # This is noise reduction, NOT semantic decision-making
        LAYOUT_ONLY = {'container', 'container-fluid', 'row', 'col', 'd-flex', 'd-none', 'd-block',
                       'd-grid', 'd-table', 'align-items-center', 'justify-content-center',
                       'flex-row', 'flex-column', 'flex-wrap', 'overflow-hidden', 'position-relative'}

        def is_meaningful(b):
            """A block is meaningful if it has content or is a structural region."""
            text = ' '.join(b['text_buf']).strip()
            has_content = len(text) > 30 or b['images'] or b['headings']
            # Structural regions are always meaningful
            if b['tag'] in ('header', 'footer', 'nav', 'main', 'section', 'article'):
                return True
            # CMS components are always meaningful
            if 'component' in ' '.join(b['classes']):
                return True
            # Blocks with content are meaningful
            if has_content:
                return True
            # Skip empty layout wrappers
            if b['classes'] and all(c.lower() in LAYOUT_ONLY or c.lower().startswith(('col-', 'd-', 'g-', 'm-', 'p-', 'text-', 'fw-', 'fs-')) for c in b['classes']):
                return False
            return False

        clean_blocks = []
        for b in self.blocks:
            if not is_meaningful(b):
                continue

            text = ' '.join(b['text_buf']).strip()

            # Determine position in page
            position = 'page'
            current = b
            while current['parentId']:
                parent = block_map.get(current['parentId'])
                if not parent:
                    break
                parent_tag = parent['tag']
                if parent_tag == 'header':
                    position = 'header'
                    break
                elif parent_tag == 'footer':
                    position = 'footer'
                    break
                elif parent_tag == 'nav':
                    position = 'nav'
                    break
                elif parent_tag == 'main':
                    position = 'main'
                    break
                current = parent

            # Get sibling types
            sibling_types = []
            if b['parentId']:
                parent = block_map.get(b['parentId'])
                if parent:
                    for cid in parent['childIds']:
                        if cid != b['id']:
                            sibling = block_map.get(cid)
                            if sibling:
                                sibling_types.append('.'.join(sibling['classes'][:2]) if sibling['classes'] else sibling['tag'])

            clean_blocks.append({
                'id': b['id'],
                'tag': b['tag'],
                'classes': b['classes'],
                'classString': ' '.join(b['classes']),
                'depth': b['depth'],
                'position': position,
                'parentId': b['parentId'],
                'childIds': b['childIds'],
                'childCount': len(b['childIds']),
                'isContainer': len(b['childIds']) > 0,
                'textContent': text[:2000],
                'textContentLength': len(text),
                'textSample': text[:300],
                'imageCount': len(b['images']),
                'linkCount': len(b['links']),
                'headingCount': len(b['headings']),
                'hasImage': bool(b['images']),
                'hasLink': bool(b['links']),
                'hasHeading': bool(b['headings']),
                'imageUrls': b['images'][:10],
                'linkUrls': b['links'][:20],
                'headingTexts': b['headings'][:5],
                'siblingTypes': sibling_types[:10],
            })

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

    parser = BlockExtractor()
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

    print(f"=== BLOCK EXTRACTION ===")
    print(f"Pages: {len(all_pages)}")
    print(f"Total blocks: {total_blocks}")
    print()
    for page in all_pages:
        blocks = page["blocks"]
        containers = [b for b in blocks if b['isContainer']]
        leaves = [b for b in blocks if not b['isContainer']]
        print(f"  {page['slug']:30s} total={len(blocks):3d}  containers={len(containers):2d}  leaves={len(leaves):2d}")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
