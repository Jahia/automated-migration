#!/usr/bin/env python3
"""source_detect.py — detect the SOURCE CMS from the captured DOM (agnostic backbone).

JahiaMigration must run first-pass on any site. The capture + media + content +
verification stages are CMS-agnostic (they work on rendered HTML). This identifies
the source CMS so the right *adapter* refines extraction (SXA field-* names, Drupal
field--name, WP entry-content, AEM cq markers). If nothing matches, the generic
DOM path is used — never a hard failure.

Detection is signature-based on the captured HTML (stable across versions):
  sitecore-sxa : /-/media/ , class="component" + field- , data-sc / sxa
  drupal       : drupal-settings-json , /sites/default/files , data-drupal
  wordpress    : wp-content , wp-json , wp-includes , class="wp-
  aem          : /etc.clientlibs/ , /content/dam/ , cq: , data-sly
  generic      : fallback (any HTML)

Usage: python3 orchestration/lib/source_detect.py <project>
Prints the detected source + writes orchestration/<project>.source.json
"""
import json, os, re, sys
from collections import Counter

SIGNATURES = [
    ("sitecore-sxa", [r"/-/media/", r'class="[^"]*\bcomponent\b', r"field-", r"data-sc-", r"\bsxa\b"]),
    ("drupal",       [r"drupal-settings-json", r"/sites/default/files", r"data-drupal", r"\bDrupal\b"]),
    ("wordpress",    [r"/wp-content/", r"/wp-json/", r"/wp-includes/", r'class="[^"]*\bwp-']),
    ("aem",          [r"/etc\.clientlibs/", r"/content/dam/", r"\bcq:", r"data-sly-", r"\bgranite\b"]),
]


def sample_html(proj, limit=8):
    """Read a sample of captured pages (agnostic capture layer)."""
    texts = []
    capdir = f"{proj}/.reference/captured"
    crawl = f"{proj}/.reference/cache/_crawl"
    roots = [capdir] if os.path.isdir(capdir) else []
    if os.path.isdir(crawl):
        roots.append(crawl)
    for root in roots:
        for dp, _, fs in os.walk(root):
            for fn in fs:
                if fn.endswith(".html"):
                    try:
                        texts.append(open(os.path.join(dp, fn), encoding="utf-8", errors="ignore").read())
                    except Exception:
                        pass
                    if len(texts) >= limit:
                        return texts
    return texts


def detect(texts):
    scores = Counter()
    for cms, sigs in SIGNATURES:
        for t in texts:
            for s in sigs:
                if re.search(s, t):
                    scores[cms] += 1
    if not scores:
        return "generic", {}
    top = scores.most_common(1)[0]
    # require at least 2 signature hits to claim a CMS, else generic
    return (top[0] if top[1] >= 2 else "generic"), dict(scores)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: source_detect.py <project>")
    project = sys.argv[1]
    proj = f"projects/{project}"
    texts = sample_html(proj)
    if not texts:
        sys.exit(f"source_detect: no captured pages under {proj}/.reference (capture first)")
    cms, scores = detect(texts)
    out = {"source": cms, "scores": scores, "sampled": len(texts),
           "note": "agnostic: media/content/verification work on any HTML; this picks the adapter"}
    outp = f"orchestration/{project}.source.json"
    json.dump(out, open(outp, "w"), indent=2)
    print(f"source_detect: {cms}  (scores={scores}, sampled {len(texts)} pages) -> {outp}")


if __name__ == "__main__":
    main()
