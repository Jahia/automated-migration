#!/usr/bin/env python3
"""hybrid-identify.py — Hybrid CMS component identification.

Uses structural matching (deterministic) + vision fallback (LLM) to identify
CMS-level components across pages. Builds a knowledge base incrementally.

Usage:
  python3 orchestration/lib/hybrid-identify.py <project> [--vision]

Approach:
  1. For each page, extract blocks (deterministic)
  2. Compute template signature (sequence of content types in <main>)
  3. Try to match against known templates
  4. If template matches: try to match each block against known components
  5. If no match: use vision (Playwright + LLM) to identify new template/components
  6. Update knowledge base

Output:
  <project>/workflow-output/knowledge-base.json
  <project>/workflow-output/template-clusters.json
  <project>/workflow-output/component-candidates.json
"""
import json
import os
import sys
import time
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    # Find the project .env file
    for arg in sys.argv[1:]:
        if not arg.startswith('--'):
            env_path = f"{arg}/.env"
            if os.path.isfile(env_path):
                load_dotenv(env_path)
                break
except ImportError:
    pass


# ── Knowledge base structure ──────────────────────────────────────

def empty_knowledge_base():
    return {
        "version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "templates": {},
        "components": {},
        "pages": {},
    }


# ── Signature computation ─────────────────────────────────────────

def compute_template_signature(blocks, block_map):
    """Compute template signature = ordered list of content types in <main>.

    Only includes blocks with actual content types (skips structural divs).
    """
    main_block = next((b for b in blocks if b['tag'] == 'main'), None)
    if not main_block:
        return []

    signature = []
    for cid in main_block.get('childBlockIds', []):
        child = block_map.get(cid)
        if not child:
            continue
        # Skip structural blocks without content types
        types = sorted(child.get('contentTypes', []))
        if types:
            signature.append('+'.join(types))
        # Skip pure div/section wrappers

    return signature


def compute_component_signature(block):
    """Compute component signature = data shape."""
    return {
        'contentTypes': sorted(block.get('contentTypes', [])),
        'hasImage': block.get('hasImage', False),
        'hasHeading': block.get('hasHeading', False),
        'hasLink': block.get('hasLink', False),
        'isContainer': block.get('isContainer', False),
        'childCount': block.get('childCount', 0),
    }


def signature_similarity(sig1, sig2):
    """Compute similarity between two template signatures (0-1).

    Uses both position-based and set-based comparison.
    """
    if not sig1 and not sig2:
        return 1.0
    if not sig1 or not sig2:
        return 0.0

    # Set-based: what content types appear in both
    set1 = set(sig1)
    set2 = set(sig2)
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0

    common = len(set1 & set2)
    total = len(set1 | set2)

    # Jaccard similarity
    jaccard = common / total if total > 0 else 0

    # Position-based: how many elements match at same position
    max_len = max(len(sig1), len(sig2))
    matches = sum(1 for i in range(min(len(sig1), len(sig2))) if sig1[i] == sig2[i])
    position_score = matches / max_len if max_len > 0 else 0

    # Length similarity (penalize very different lengths)
    len_ratio = min(len(sig1), len(sig2)) / max_len if max_len > 0 else 1.0

    # Weighted combination
    return 0.5 * jaccard + 0.3 * position_score + 0.2 * len_ratio


def component_signature_match(sig1, sig2):
    """Check if two component signatures match."""
    # Same content types
    if sig1['contentTypes'] != sig2['contentTypes']:
        return False

    # Same container status
    if sig1['isContainer'] != sig2['isContainer']:
        return False

    # Close child count (within 2)
    if abs(sig1['childCount'] - sig2['childCount']) > 2:
        return False

    return True


# ── Template matching ─────────────────────────────────────────────

def find_matching_template(signature, kb, threshold=0.5):
    """Find a matching template in the knowledge base."""
    best_match = None
    best_score = 0.0

    for tid, template in kb['templates'].items():
        score = signature_similarity(signature, template['signature'])
        if score > best_score and score >= threshold:
            best_score = score
            best_match = tid

    return best_match, best_score


# ── Component matching ────────────────────────────────────────────

def find_matching_component(signature, kb):
    """Find a matching component in the knowledge base."""
    for cid, component in kb['components'].items():
        if component_signature_match(signature, component['signature']):
            return cid
    return None


# ── Vision fallback ───────────────────────────────────────────────

OVH_API_KEY = os.environ.get("OVH_API_KEY", "")
OVH_ENDPOINT = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
VISION_MODEL = "Qwen2.5-VL-72B-Instruct"


def vision_identify(page_url, page_slug):
    """Use Playwright + Qwen2.5-VL to identify CMS components on a page.

    Takes a screenshot, sends it to the vision model, and parses the response.
    Returns a dict with template info and component list.
    """
    import subprocess
    import base64
    import requests

    # Step 1: Take screenshot with Playwright
    screenshot_path = f"/tmp/vision-{page_slug}.png"
    screenshot_script = f"""
const {{ chromium }} = require('playwright');
(async () => {{
    const browser = await chromium.launch({{ headless: true }});
    const page = await browser.newPage({{ viewport: {{ width: 1440, height: 900 }} }});
    await page.goto('{page_url}', {{ waitUntil: 'networkidle', timeout: 30000 }});
    await page.waitForTimeout(3000);
    await page.screenshot({{ path: '{screenshot_path}', fullPage: true }});
    console.log('OK');
    await browser.close();
}})();
"""
    try:
        result = subprocess.run(
            ['node', '-e', screenshot_script],
            capture_output=True, text=True, timeout=60,
            cwd=os.getcwd()
        )
        if result.returncode != 0:
            print(f"  Screenshot failed: {result.stderr[:100]}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"  Screenshot error: {e}", file=sys.stderr)
        return None

    # Step 2: Read and encode screenshot
    try:
        with open(screenshot_path, 'rb') as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode()
    except Exception as e:
        print(f"  Screenshot read error: {e}", file=sys.stderr)
        return None

    # Step 3: Send to vision model
    prompt = """Analyze this webpage screenshot and identify the CMS components visible.

For each component you see, provide:
1. Name (e.g., HeroBanner, ContentBlock, Navigation, Footer)
2. Content types it contains (heading, image, text, link, list)
3. Position on page (header, main, footer)
4. Approximate Y position (pixels from top)

Also identify:
- The page template type (home, listing, content, section-hub)
- Any cross-cutting components (header, footer, nav)

Reply in this JSON format:
{
  "template_type": "home|listing|content|section-hub",
  "components": [
    {
      "name": "ComponentName",
      "contentTypes": ["heading", "image", "text"],
      "position": "header|main|footer",
      "y_position": 0,
      "description": "Brief description"
    }
  ],
  "crossCutting": ["header", "footer", "nav"]
}"""

    try:
        resp = requests.post(
            OVH_ENDPOINT,
            headers={
                "Authorization": f"Bearer {OVH_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                        ]
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.1
            },
            timeout=60
        )

        if resp.status_code != 200:
            print(f"  Vision API error: HTTP {resp.status_code}", file=sys.stderr)
            return None

        data = resp.json()
        content = data['choices'][0]['message']['content']

        # Parse JSON from response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return {'raw_response': content}

    except Exception as e:
        print(f"  Vision API error: {e}", file=sys.stderr)
        return None


# ── Main orchestrator ─────────────────────────────────────────────

def process_page(page, kb, use_vision=False):
    """Process a single page against the knowledge base."""
    blocks = page.get('blocks', [])
    block_map = {b['id']: b for b in blocks}

    # Compute template signature
    signature = compute_template_signature(blocks, block_map)

    # Try to match template
    template_match, score = find_matching_template(signature, kb)

    result = {
        'page': page['slug'],
        'template_match': template_match,
        'template_score': score,
        'new_components': [],
        'matched_components': [],
    }

    if template_match:
        # Template matched — try to match each component
        template = kb['templates'][template_match]

        # Get main content blocks
        main_block = next((b for b in blocks if b['tag'] == 'main'), None)
        if main_block:
            for cid in main_block.get('childBlockIds', []):
                child = block_map.get(cid)
                if not child:
                    continue

                comp_sig = compute_component_signature(child)
                comp_match = find_matching_component(comp_sig, kb)

                if comp_match:
                    # Add instance to existing component
                    kb['components'][comp_match]['instances'].append({
                        'page': page['slug'],
                        'blockId': child['id'],
                        'textSample': child.get('textSample', '')[:100],
                    })
                    result['matched_components'].append(comp_match)
                else:
                    # New component — try vision or create generic
                    if use_vision:
                        print(f"    Vision: identifying {child['id']} ({child.get('classString', '')[:30]})...", file=sys.stderr)
                        vision = vision_identify(page.get('url', ''), page['slug'])
                        if vision:
                            result['new_components'].append({
                                'blockId': child['id'],
                                'vision': vision,
                            })

                    # Create new component from structure
                    new_id = f"comp_{len(kb['components']) + 1:03d}"
                    kb['components'][new_id] = {
                        'id': new_id,
                        'signature': comp_sig,
                        'instances': [{
                            'page': page['slug'],
                            'blockId': child['id'],
                            'textSample': child.get('textSample', '')[:100],
                        }],
                        'discovered_from': 'vision' if use_vision else 'structural',
                    }
                    result['new_components'].append(new_id)

        # Add page to template
        template['pages'].append(page['slug'])

    else:
        # No template match — use vision to identify template and components
        vision_result = None
        if use_vision:
            print(f"    Vision: new template for {page['slug']}...", file=sys.stderr)
            vision_result = vision_identify(page.get('url', ''), page['slug'])

        # Create new template
        new_template_id = f"template_{len(kb['templates']) + 1:03d}"

        # Get main content blocks for components
        main_block = next((b for b in blocks if b['tag'] == 'main'), None)
        component_ids = []

        if main_block:
            for cid in main_block.get('childBlockIds', []):
                child = block_map.get(cid)
                if not child:
                    continue

                comp_sig = compute_component_signature(child)
                comp_match = find_matching_component(comp_sig, kb)

                if comp_match:
                    kb['components'][comp_match]['instances'].append({
                        'page': page['slug'],
                        'blockId': child['id'],
                        'textSample': child.get('textSample', '')[:100],
                    })
                    component_ids.append(comp_match)
                    result['matched_components'].append(comp_match)
                else:
                    new_id = f"comp_{len(kb['components']) + 1:03d}"
                    kb['components'][new_id] = {
                        'id': new_id,
                        'signature': comp_sig,
                        'instances': [{
                            'page': page['slug'],
                            'blockId': child['id'],
                            'textSample': child.get('textSample', '')[:100],
                        }],
                        'discovered_from': 'vision' if use_vision else 'structural',
                        'vision_data': vision_result.get('components', []) if vision_result else [],
                    }
                    component_ids.append(new_id)
                    result['new_components'].append(new_id)

        kb['templates'][new_template_id] = {
            'id': new_template_id,
            'signature': signature,
            'pages': [page['slug']],
            'components': component_ids,
            'discovered_from': 'vision' if use_vision and not template_match else 'structural',
        }
        result['template_match'] = new_template_id

    # Record page
    kb['pages'][page['slug']] = {
        'template': result['template_match'],
        'url': page.get('url', ''),
        'processed_at': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: hybrid-identify.py <project> [--vision]", file=sys.stderr)
        sys.exit(1)

    proj = sys.argv[1]
    use_vision = '--vision' in sys.argv

    blocks_path = f"{proj}/workflow-output/html-blocks.json"
    if not os.path.isfile(blocks_path):
        print(f"FAIL: {blocks_path} not found (run extract-blocks first)", file=sys.stderr)
        sys.exit(1)

    blocks_data = json.load(open(blocks_path))
    pages = blocks_data.get('pages', [])

    if not pages:
        print("FAIL: 0 pages", file=sys.stderr)
        sys.exit(1)

    # Load or create knowledge base
    kb_path = f"{proj}/workflow-output/knowledge-base.json"
    if os.path.isfile(kb_path):
        kb = json.load(open(kb_path))
        print(f"Loaded existing knowledge base: {len(kb['templates'])} templates, {len(kb['components'])} components")
    else:
        kb = empty_knowledge_base()

    # Process each page
    print(f"\n=== HYBRID IDENTIFICATION ===")
    print(f"Pages: {len(pages)}, Vision: {'ON' if use_vision else 'OFF'}")
    print()

    results = []
    for page in pages:
        result = process_page(page, kb, use_vision)
        results.append(result)

        template = result['template_match']
        score = result['template_score']
        matched = len(result['matched_components'])
        new = len(result['new_components'])

        status = "MATCH" if score > 0.7 else "NEW"
        print(f"  {page['slug']:35s} {status} template={template or '?':15s} score={score:.2f}  matched={matched}  new={new}")

    # Save knowledge base
    kb['updated_at'] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    os.makedirs(os.path.dirname(kb_path), exist_ok=True)
    with open(kb_path, 'w') as f:
        json.dump(kb, f, indent=2)

    # Generate template-clusters.json
    clusters = []
    for tid, template in kb['templates'].items():
        clusters.append({
            'clusterId': tid,
            'description': f'Template with {len(template["signature"])} main sections',
            'pages': template['pages'],
            'signature': template['signature'],
            'components': template.get('components', []),
        })

    clusters_output = {
        'clusters': clusters,
        'crossCutting': {},  # Will be filled by LLM analysis
    }
    with open(f"{proj}/workflow-output/template-clusters.json", 'w') as f:
        json.dump(clusters_output, f, indent=2)

    # Generate component-candidates.json
    candidates = []
    for cid, comp in kb['components'].items():
        sig = comp['signature']
        candidates.append({
            'candidateId': cid,
            'frequency': len(comp['instances']),
            'dataShape': sig['contentTypes'],
            'hasImage': sig['hasImage'],
            'hasHeading': sig['hasHeading'],
            'hasLink': sig['hasLink'],
            'isContainer': sig['isContainer'],
            'instances': comp['instances'],
        })

    candidates_output = {
        'totalCandidates': len(candidates),
        'components': candidates,
    }
    with open(f"{proj}/workflow-output/component-candidates.json", 'w') as f:
        json.dump(candidates_output, f, indent=2)

    # Summary
    print(f"\n{'='*50}")
    print(f"KNOWLEDGE BASE")
    print(f"  Templates: {len(kb['templates'])}")
    print(f"  Components: {len(kb['components'])}")
    print(f"  Pages processed: {len(kb['pages'])}")
    print(f"\nOutputs:")
    print(f"  {kb_path}")
    print(f"  {proj}/workflow-output/template-clusters.json")
    print(f"  {proj}/workflow-output/component-candidates.json")


if __name__ == "__main__":
    main()
