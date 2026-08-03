#!/usr/bin/env python3
"""entity-coverage.py — the source's own URL inventory must be fully accounted for.

Two different completeness questions, and only the second one this gate answers:

  * link-census asks: does every LINK have a destination in the model?
  * entity-coverage asks: is every URL the SOURCE PUBLISHES accounted for?

They are not the same. A sitemap family can be linked from nowhere in the captured
DOM and still be real content — measured on salonphoto (2026-08-03): 7 press releases
under presse-createur-contenus/communiques-dossiers-presse were invisible to the menu
crawl AND to the link census (their only in-page links live in the footer), and the
actus listing linked 9 details while the sitemap enumerated 57. A migration driven off
the capture alone ships a fraction of the news and every other gate stays green.

FAILS when:
  1. sitemap-urls.json is missing (sitemap_enumerate never ran),
  2. any sitemap family is UNACCOUNTED — neither a captured page, a declared entity
     prefix, a declared page-to-crawl, nor an accepted target,
  3. `--expect` is passed and the LIVE per-folder mainResource counts fall short of
     the sitemap's expected counts (the load-completeness check, post-load).

Usage: entity-coverage.py <project> [--expect <site> [--locale fr]]
"""
import argparse
import json
import subprocess
import sys


def live_counts(site, locale, folders):
    """LIVE mainResource node counts per folder, via the Jahia MCP/GraphQL read path."""
    out = {}
    for folder, spec in folders.items():
        base = spec.get("_contentPath") or f"/sites/{site}/contents/{folder}"
        q = ('{jcr(workspace:EDIT){nodeByPath(path:"%s"){children{nodes{name}}}}}' % base)
        r = subprocess.run(
            ["bash", "-c",
             'set -a; . .env.local 2>/dev/null; set +a; '
             f'curl -s -u "$JAHIA_USER:$JAHIA_PASS" -H "Origin: $JAHIA_URL" '
             f'-H "Content-Type: application/json" -X POST "$JAHIA_URL/modules/graphql" '
             f"-d '{json.dumps({'query': q})}'"],
            capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            nodes = (((d.get("data") or {}).get("jcr") or {}).get("nodeByPath") or {})
            out[folder] = len((nodes.get("children") or {}).get("nodes") or [])
        except (ValueError, AttributeError):
            out[folder] = 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--expect", metavar="SITE", default="",
                    help="also assert LIVE per-folder counts reach the sitemap's "
                         "expected counts (run after the entity load)")
    ap.add_argument("--locale", default="")
    a = ap.parse_args()
    p = a.project
    path = f"projects/{p}/workflow-output/sitemap-urls.json"
    try:
        s = json.load(open(path))
    except (OSError, ValueError) as e:
        sys.exit(f"FAIL entity-coverage: cannot read {path} ({e}) — run "
                 f"orchestration/lib/sitemap_enumerate.py {p} first")

    fails = []
    unacc = s.get("unaccounted") or {}
    if unacc:
        tot = sum(unacc.values())
        fails.append(f"{tot} sitemap URL(s) in {len(unacc)} family/families are "
                     f"UNACCOUNTED: " + ", ".join(f"{k} ({v})" for k, v in
                                                  list(unacc.items())[:6]))

    expected = s.get("expectedEntityCounts") or {}
    if a.expect and expected:
        try:
            folders = (json.load(open(f"orchestration/content/{p}.mainresource.json"))
                       .get("folders") or {})
        except (OSError, ValueError):
            folders = {}
        live = live_counts(a.expect, a.locale, {k: folders.get(k, {}) for k in expected})
        short = {k: (live.get(k, 0), v) for k, v in expected.items()
                 if live.get(k, 0) < v}
        if short:
            fails.append("entity load short of the source: " + ", ".join(
                f"{k} {got}/{want}" for k, (got, want) in short.items()))

    if fails:
        print(f"FAIL entity-coverage [{p}] — sitemap {s.get('source')}, "
              f"{s.get('localeUrls')} locale URL(s)")
        for f in fails:
            print(f"  - {f}")
        print("  Fix: declare the family as an entity prefix, a page to crawl, or an "
              "accepted target with a reason — or load the missing entities.")
        sys.exit(1)
    msg = (f"PASS entity-coverage: {s.get('localeUrls')} sitemap URL(s), "
           f"{len(s.get('families') or {})} families, all accounted")
    if expected:
        msg += " | expected entity counts: " + ", ".join(
            f"{k}={v}" for k, v in expected.items())
    print(msg)


if __name__ == "__main__":
    main()
