#!/usr/bin/env python3
"""extract-blocks.py — Deterministic CMS component extraction.

Identifies CMS-level components using three deterministic signals:

1. CMS-declared: class contains "component" (Sitecore SXA, Drupal blocks, WP widgets)
2. Structural regions: <header>, <footer>, <nav>, <main>, <section>, <article>
3. Content mixing: blocks with 2+ different content types (heading, media, text, interactive)

The LLM then decides: which are templates, which are cross-cutting, which are
MainResource, which should be merged into the same CND type.

Usage:
  python3 orchestration/lib/extract-blocks.py <project>

Output:
  <project>/workflow-output/html-blocks.json
"""
import json
import os
import sys
import time
from html.parser import HTMLParser


HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
MEDIA_TAGS = {'img', 'video', 'picture', 'source', 'canvas', 'svg', 'iframe'}
INTERACTIVE_TAGS = {'a', 'button', 'input', 'select', 'textarea'}
STRUCTURAL_TAGS = {'header', 'footer', 'nav', 'main', 'section', 'article', 'aside', 'form'}


class CMSComponentExtractor(HTMLParser):
    """Extract CMS-level components from HTML."""

    def __init__(self):
        super().__init__()
        self.blocks = []
        self.tag_stack = []  # dicts with block_id, tag, depth, childTags
        self.depth = 0
        self.block_counter = 0
        self._current_heading = None

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        attrs_d = dict(attrs)
        classes = attrs_d.get('class', '').split()
        class_str = attrs_d.get('class', '')

        is_component = False

        # Signal 1: CMS-declared component
        if 'component' in classes:
            is_component = True
        # Signal 2: Structural region
        elif tag in STRUCTURAL_TAGS:
            is_component = True
        # Signal 3: Div with semantic class (hero, carousel, grid, etc.)
        elif tag == 'div' and any(
            k in class_str.lower() for k in [
                'hero', 'banner', 'slider', 'carousel', 'gallery', 'grid',
                'listing', 'cards', 'push', 'teaser', 'widget', 'block',
                'module', 'feature', 'testimonial', 'faq', 'accordion', 'tabs',
                'map', 'video', 'social', 'newsletter', 'search', 'breadcrumb',
                'cta', 'call-to-action', 'pricing', 'team', 'portfolio',
                'footer', 'header', 'nav',
            ]
        ):
            is_component = True

        if is_component:
            self.block_counter += 1
            block_id = f"block_{self.block_counter:03d}"
            parent_id = self.tag_stack[-1]['block_id'] if self.tag_stack else None

            block = {
                'id': block_id,
                'tag': tag,
                'classes': classes,
                'classString': class_str,
                'depth': self.depth,
                'parentId': parent_id,
                'childBlockIds': [],
                'childTags': [],
                'text_buf': [],
                'images': [],
                'links': [],
                'headings': [],
            }
            self.blocks.append(block)
            self.tag_stack.append({'block_id': block_id, 'tag': tag, 'depth': self.depth})

        # Track child tags
        if self.tag_stack:
            self.tag_stack[-1].setdefault('childTags', []).append(tag)

        # Track content
        if tag in MEDIA_TAGS:
            src = attrs_d.get('src', '') or attrs_d.get('data-src', '') or attrs_d.get('data-lazy-src', '')
            if src and not src.startswith('data:') and self.tag_stack:
                for b in reversed(self.blocks):
                    if b['id'] == self.tag_stack[-1]['block_id']:
                        b['images'].append(src)
                        break
        elif tag in INTERACTIVE_TAGS:
            href = attrs_d.get('href', '')
            if href and not href.startswith('#') and not href.startswith('javascript:') and self.tag_stack:
                for b in reversed(self.blocks):
                    if b['id'] == self.tag_stack[-1]['block_id']:
                        b['links'].append(href)
                        break
        elif tag in HEADING_TAGS:
            self._current_heading = tag

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1]['tag'] == tag and self.tag_stack[-1]['depth'] == self.depth:
            popped = self.tag_stack.pop()
            block_id = popped['block_id']
            if self.tag_stack:
                parent_id = self.tag_stack[-1]['block_id']
                for b in self.blocks:
                    if b['id'] == parent_id:
                        b['childBlockIds'].append(block_id)
                        break

        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return

        if self.tag_stack:
            current_id = self.tag_stack[-1]['block_id']
            for b in self.blocks:
                if b['id'] == current_id:
                    b['text_buf'].append(text)
                    break

        if self._current_heading:
            if self.tag_stack:
                current_id = self.tag_stack[-1]['block_id']
                for b in self.blocks:
                    if b['id'] == current_id:
                        b['headings'].append(text[:200])
                        break
            self._current_heading = None

    def get_result(self, page_slug, page_url):
        block_map = {b['id']: b for b in self.blocks}

        # Compute content types for each block
        for b in self.blocks:
            b['contentTypes'] = set()
            b['textContent'] = ' '.join(b['text_buf']).strip()

            if b['headings']:
                b['contentTypes'].add('heading')
            if b['images']:
                b['contentTypes'].add('media')
            if len(b['textContent']) > 30:
                b['contentTypes'].add('text')
            if b['links']:
                b['contentTypes'].add('interactive')

        # Keep blocks that are:
        # 1. CMS components (class contains 'component')
        # 2. Structural regions (header, footer, nav, main, section, article)
        # 3. Blocks with 2+ content types (mixed content = semantic unit)
        clean_blocks = []
        for b in self.blocks:
            is_cms = 'component' in b['classes']
            is_structural = b['tag'] in STRUCTURAL_TAGS
            has_mix = len(b['contentTypes']) >= 2

            if is_cms or is_structural or has_mix:
                # Determine position
                position = 'page'
                current = b
                while current['parentId']:
                    parent = block_map.get(current['parentId'])
                    if not parent:
                        break
                    if parent['tag'] in STRUCTURAL_TAGS:
                        position = parent['tag']
                        break
                    current = parent

                # Sibling types
                sibling_types = []
                if b['parentId']:
                    parent = block_map.get(b['parentId'])
                    if parent:
                        for cid in parent['childBlockIds']:
                            if cid != b['id']:
                                sibling = block_map.get(cid)
                                if sibling:
                                    st = sibling['classString'][:50] if sibling['classes'] else sibling['tag']
                                    sibling_types.append(st)

                clean_blocks.append({
                    'id': b['id'],
                    'tag': b['tag'],
                    'classes': b['classes'],
                    'classString': b['classString'],
                    'depth': b['depth'],
                    'position': position,
                    'parentId': b['parentId'],
                    'childBlockIds': b['childBlockIds'],
                    'childCount': len(b['childBlockIds']),
                    'isContainer': len(b['childBlockIds']) > 0,
                    'contentTypes': sorted(b['contentTypes']),
                    'contentTypeCount': len(b['contentTypes']),
                    'textContent': b['textContent'][:2000],
                    'textContentLength': len(b['textContent']),
                    'textSample': b['textContent'][:300],
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

        return {
            'slug': page_slug,
            'url': page_url,
            'blocks': clean_blocks,
            'totalBlocks': len(clean_blocks),
            'rootBlocks': len(roots),
            'globalStructure': {
                'hasHeader': any(b['tag'] == 'header' for b in clean_blocks),
                'hasFooter': any(b['tag'] == 'footer' for b in clean_blocks),
                'hasNav': any(b['tag'] == 'nav' for b in clean_blocks),
                'hasMain': any(b['tag'] == 'main' for b in clean_blocks),
            }
        }


def extract_blocks_from_page(html_path, page_slug, page_url):
    try:
        with open(html_path, 'r', errors='replace') as f:
            html = f.read()
    except Exception:
        return None

    parser = CMSComponentExtractor()
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

    print(f"=== CMS COMPONENT EXTRACTION ===")
    print(f"Pages: {len(all_pages)}")
    print(f"Total components: {total_blocks}")
    print()
    for page in all_pages:
        blocks = page["blocks"]
        by_types = {}
        for b in blocks:
            key = '+'.join(b['contentTypes']) if b['contentTypes'] else 'structural'
            by_types[key] = by_types.get(key, 0) + 1
        print(f"  {page['slug']:30s} components={len(blocks):3d}")
        for k, v in sorted(by_types.items(), key=lambda x: -x[1])[:5]:
            print(f"    {k:35s} ×{v}")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
