#!/usr/bin/env python3
"""build_nav_tree.py — DETERMINISTIC hierarchical page tree from the sitemap.

The AIStartupKit navigation pattern requires the main navigation to be DRIVEN
BY THE PAGE TREE (3 levels, a Jahia navigation-menu component — never frozen
markup). create_pages builds a FLAT tree from the crawl inventory; this script
restructures it per orchestration/sitemaps/<project>.txt:

  * one-segment paths that do not exist yet -> new SECTION pages (jnt:page,
    `basic` template, en+fr titles from NAV_TITLES below / the segment name)
  * multi-segment paths whose leaf exists elsewhere -> the page is MOVED under
    its sitemap parent (GraphQL jcr.moveNode; MCP has no move)
  * L1 order under /home == sitemap order (GraphQL reorderChildren — the MCP
    orderBefore no-ops, observed live)
  * everything touched is (re)published in en+fr

Idempotent: existing pages at their target path are left alone.
Usage: build_nav_tree.py <project> <site> [--locale en] [--dry]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP  # noqa: E402

# en/fr titles for the NEW section pages (nav labels come from jcr:title).
NAV_TITLES = {
    "offers": {"en": "Offers", "fr": "Offres"},
    "brands": {"en": "Brands", "fr": "Marques"},
    "meetings-and-events": {"en": "Meetings & Events", "fr": "Réunions & Événements"},
    "about-the-ascott-limited": {"en": "About The Ascott Limited",
                                 "fr": "À propos de The Ascott Limited"},
}


def sitemap_paths(project):
    out = []
    try:
        for line in open(f"orchestration/sitemaps/{project}.txt"):
            line = line.strip()
            if not line or line.startswith("#") or line == "home":
                continue
            out.append(line)
    except FileNotFoundError:
        pass   # no sitemap = flat site: the step is a no-op, not an error
    return out


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: build_nav_tree.py <project> <site> [--locale en] [--dry]")
    project, site = sys.argv[1], sys.argv[2]
    locale = sys.argv[sys.argv.index("--locale") + 1] if "--locale" in sys.argv else "en"
    other = "fr" if locale != "fr" else "en"
    dry = "--dry" in sys.argv
    m = MCP(project)
    home = f"/sites/{site}/home"

    paths = sitemap_paths(project)
    created = moved = published = 0

    def exists(path):
        try:
            r = m.get(path, locale=locale)
            return not (isinstance(r, dict) and r.get("error"))
        except Exception:
            return False

    # ── pass 1: sections + moves, in sitemap order (parents precede children) ──
    for rel in paths:
        target = f"{home}/{rel}"
        leaf = rel.split("/")[-1]
        parent = f"{home}/{'/'.join(rel.split('/')[:-1])}".rstrip("/")
        if exists(target):
            continue
        if exists(f"{home}/{leaf}") and leaf != rel:
            # crawled page sitting flat under /home -> MOVE under its section
            if dry:
                print(f"[dry] move {home}/{leaf} -> {parent}/")
            else:
                r = m.gql('mutation { jcr(workspace: EDIT) { moveNode(pathOrId: "%s", '
                          'destParentPathOrId: "%s") { node { path } } } }'
                          % (f"{home}/{leaf}", parent))
                if isinstance(r, dict) and r.get("errors"):
                    print(f"  ! move {leaf}: {str(r['errors'])[:140]}", file=sys.stderr)
                    continue
                print(f"  ~ moved {leaf} -> {parent}/")
            moved += 1
            continue
        # new SECTION page
        titles = NAV_TITLES.get(leaf, {})
        t_loc = titles.get(locale) or leaf.replace("-", " ").title()
        t_oth = titles.get(other) or t_loc
        if dry:
            print(f"[dry] create section {target} ('{t_loc}')")
        else:
            try:
                m.create(parent, "jnt:page",
                         {"jcr:title": t_loc, "j:templateName": "basic"},
                         name=leaf, locale=locale)
                m.update(target, {"jcr:title": t_oth}, locale=other)
                print(f"  + section {target} ('{t_loc}')")
            except Exception as e:
                print(f"  ! section {leaf}: {str(e)[:140]}", file=sys.stderr)
                continue
        created += 1

    # ── pass 2: L1 order under /home == sitemap L1 order ──
    l1 = [p for p in paths if "/" not in p]
    if not dry and l1:
        names = json.dumps(l1)
        r = m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s") '
                  '{ reorderChildren(names: %s, position: FIRST) } } }' % (home, names))
        if isinstance(r, dict) and r.get("errors"):
            print(f"  ! reorder: {str(r['errors'])[:140]}", file=sys.stderr)
        else:
            print(f"  ~ L1 order: {', '.join(l1)}")

    # ── pass 3: publish every sitemap path (+ home, for the reorder) ──
    if not dry:
        for rel in ["", *paths]:
            path = home if not rel else f"{home}/{rel}"
            try:
                m.publish(path, languages=(locale, other))
                published += 1
            except Exception as e:
                print(f"  ! publish {path}: {str(e)[:120]}", file=sys.stderr)

    print(f"build_nav_tree: {created} section(s) created, {moved} page(s) moved, "
          f"{published} publish(es)")


if __name__ == "__main__":
    main()
