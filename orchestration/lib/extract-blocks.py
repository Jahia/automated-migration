#!/usr/bin/env python3
"""extract-blocks.py — Deterministic, CMS-agnostic HTML block extraction.

Extracts ALL structural blocks from crawled HTML pages WITHOUT making any
decisions about what they are. Pure data extraction — no heuristics, no
CMS-specific patterns, no semantic judgment.

The LLM analyzes the output and decides: template clusters, component types,
MainResource, cross-cutting, etc.

Usage:
  python3 orchestration/lib/extract-blocks.py <project>

Input:
  <project>/workflow-output/page-inventory.json
  <project>/.reference/cache/_crawl/  (HTML files)

Output:
  <project>/workflow-output/html-blocks.json

Output format per page:
{
  "slug": "home",
  "url": "https://...",
  "title": "Page Title",
  "blocks": [
    {
      "id": "block_001",
      "tag": "div",
      "classes": ["component", "hero-banner", "container-fluid"],
      "depth": 3,
      "parentTag": "main",
      "parentClasses": ["content-area"],
      "childTags": ["h1", "p", "img", "a"],
      "textContent": "Heading text\nParagraph text...",
      "hasImage": true,
      "hasLink": true,
      "hasHeading": true,
      "imageUrls": ["https://..."],
      "linkUrls": ["/fr-FR/page"],
      "headingTexts": ["Main Heading"],
      "htmlSnippet": "<div class=\"component hero-banner\">...</div>"
    }
  ],
  "globalStructure": {
    "hasHeader": true,
    "hasFooter": true,
    "hasNav": true,
    "hasMain": true,
    "headerBlocks": ["block_001", "block_002"],
    "footerBlocks": ["block_050"],
    "navBlocks": ["block_003"],
    "mainBlocks": ["block_010", "block_011", ...]
  }
}
"""
import json
import os
import re
import sys
import time
from html.parser import HTMLParser


class BlockExtractor(HTMLParser):
    """Extract all structural blocks from HTML without making decisions."""

    # Tags that represent structural blocks
    BLOCK_TAGS = {
        'div', 'section', 'article', 'aside', 'nav', 'header', 'footer',
        'main', 'form', 'table', 'ul', 'ol', 'figure', 'details', 'dialog',
        'fieldset', 'blockquote', 'dl',
    }

    # Tags that contain text content
    TEXT_TAGS = {'p', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'td', 'th', 'dt', 'dd', 'label', 'caption', 'figcaption', 'pre', 'code'}

    def __init__(self):
        super().__init__()
        self.blocks = []
        self.tag_stack = []  # (tag, classes, block_index)
        self.current_text = ""
        self.current_images = []
        self.current_links = []
        self.current_headings = []
        self.block_counter = 0
        self.in_block = False
        self.depth = 0

        # Global structure tracking
        self.has_header = False
        self.has_footer = False
        self.has_nav = False
        self.has_main = False
        self.header_blocks = []
        self.footer_blocks = []
        self.nav_blocks = []
        self.main_blocks = []

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        attrs_d = dict(attrs)
        classes = attrs_d.get('class', '').split()

        # Track global structure
        if tag == 'header':
            self.has_header = True
        elif tag == 'footer':
            self.has_footer = True
        elif tag == 'nav':
            self.has_nav = True
        elif tag == 'main':
            self.has_main = True

        # Check if this is a block-level element
        if tag in self.BLOCK_TAGS:
            self.block_counter += 1
            block_id = f"block_{self.block_counter:03d}"

            # Get parent info
            parent_tag = self.tag_stack[-1][0] if self.tag_stack else None
            parent_classes = self.tag_stack[-1][1] if self.tag_stack else []

            # Start collecting data for this block
            self.tag_stack.append((tag, classes, block_id))
            self.current_text = ""
            self.current_images = []
            self.current_links = []
            self.current_headings = []

            # Create block object
            block = {
                'id': block_id,
                'tag': tag,
                'classes': classes,
                'depth': self.depth,
                'parentTag': parent_tag,
                'parentClasses': parent_classes[:5],
                'childTags': [],
                'textContent': '',
                'hasImage': False,
                'hasLink': False,
                'hasHeading': False,
                'imageUrls': [],
                'linkUrls': [],
                'headingTexts': [],
                'htmlSnippet': '',
            }
            self.blocks.append(block)

            # Track in global structure
            if tag == 'header':
                self.header_blocks.append(block_id)
            elif tag == 'footer':
                self.footer_blocks.append(block_id)
            elif tag == 'nav':
                self.nav_blocks.append(block_id)
            elif tag == 'main':
                self.main_blocks.append(block_id)

        # Track child tags and content
        if self.tag_stack:
            current_block = self.blocks[self.tag_stack[-1][2]] if isinstance(self.tag_stack[-1][2], int) else None
            # Find the block by id
            for b in self.blocks:
                if b['id'] == self.tag_stack[-1][2]:
                    if tag not in b['childTags']:
                        b['childTags'].append(tag)
                    break

        # Track images
        if tag == 'img':
            src = attrs_d.get('src', '')
            if src and not src.startswith('data:'):
                if self.tag_stack:
                    for b in self.blocks:
                        if b['id'] == self.tag_stack[-1][2]:
                            b['hasImage'] = True
                            b['imageUrls'].append(src)
                            break

        # Track links
        if tag == 'a':
            href = attrs_d.get('href', '')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                if self.tag_stack:
                    for b in self.blocks:
                        if b['id'] == self.tag_stack[-1][2]:
                            b['hasLink'] = True
                            b['linkUrls'].append(href)
                            break

        # Track headings
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            if self.tag_stack:
                for b in self.blocks:
                    if b['id'] == self.tag_stack[-1][2]:
                        b['hasHeading'] = True
                        break

    def handle_endtag(self, tag):
        # Finalize block if we're closing a block-level element
        if tag in self.BLOCK_TAGS and self.tag_stack:
            block_id = self.tag_stack[-1][2]
            for b in self.blocks:
                if b['id'] == block_id:
                    b['textContent'] = self.current_text.strip()[:2000]
                    break
            self.tag_stack.pop()

        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.current_text += text + "\n"

            # Track heading text
            if self.tag_stack:
                for b in self.blocks:
                    if b['id'] == self.tag_stack[-1][2]:
                        if b['hasHeading'] and len(text) > 2:
                            b['headingTexts'].append(text[:200])
                        break

    def get_result(self, page_slug, page_url):
        """Return the extracted blocks with global structure."""
        # Clean up blocks
        for block in self.blocks:
            # Remove internal tracking fields
            block.pop('htmlSnippet', None)

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
                'headerBlocks': self.header_blocks,
                'footerBlocks': self.footer_blocks,
                'navBlocks': self.nav_blocks,
                'mainBlocks': self.main_blocks,
            }
        }


def extract_blocks_from_page(html_path, page_slug, page_url):
    """Extract all blocks from a single HTML page."""
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

    # Extract blocks from all pages
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

    # Write output
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

    # Report
    print(f"=== BLOCK EXTRACTION ===")
    print(f"Pages: {len(all_pages)}")
    print(f"Total blocks: {total_blocks}")
    print()
    for page in all_pages[:5]:
        blocks = page["blocks"]
        with_img = sum(1 for b in blocks if b["hasImage"])
        with_link = sum(1 for b in blocks if b["hasLink"])
        with_heading = sum(1 for b in blocks if b["hasHeading"])
        print(f"  {page['slug']:30s} blocks={len(blocks):4d}  img={with_img:3d}  links={with_link:3d}  headings={with_heading:3d}")
    if len(all_pages) > 5:
        print(f"  ... and {len(all_pages) - 5} more pages")
    print(f"\nOutput: {out_path}")
    print(f"\nNext step: feed html-blocks.json to the LLM for semantic analysis")


if __name__ == "__main__":
    main()
