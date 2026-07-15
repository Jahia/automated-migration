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
import re
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
        pass   # no explicit sitemap: fall back to the crawl URL hierarchy
    return out


def inventory_paths(project):
    """Derive the nested page hierarchy from the CRAWL URLs when no explicit
    sitemap file exists — so a flat crawl still becomes a real 3-level tree
    (the nav is the tree). A page at .../corporate/careers has the flat slug
    'corporate_careers' (create_pages' name == URL segments joined by '_'); to
    nest it we emit the rel path 'corporate/corporate_careers' so its LEAF ==
    the existing flat slug and build_nav_tree MOVES that page under 'corporate'
    (never recreates it). Parents (fewer segments) come first so a section
    exists before its children are moved under it."""
    inv_p = f"projects/{project}/workflow-output/page-inventory.json"
    try:
        inv = json.load(open(inv_p))
    except (FileNotFoundError, ValueError):
        return []
    rels = set()
    for p in inv.get("pages", []):
        segs = [s for s in re.sub(r"^https?://[^/]+", "", p.get("url") or "").split("/") if s]
        if not segs:
            continue  # home
        # emit EVERY ancestor rel + the page rel, so a parent segment that was
        # never crawled on its own (e.g. /receiving exists only via
        # /receiving/mail-redirection-service) still gets a SECTION page created
        # before its child is moved under it. Each rel's leaf is the flat slug
        # (URL segments joined by '_') so an existing flat page is MOVED, and a
        # missing ancestor is CREATED.
        for depth in range(len(segs)):
            rels.add("/".join("_".join(segs[: i + 1]) for i in range(depth + 1)))
    return sorted(rels, key=lambda r: (r.count("/"), r))


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
    src = "sitemap file"
    if not paths:
        paths = inventory_paths(project)
        src = "crawl URL hierarchy"
        # PERSIST the derived hierarchy as the project sitemap: create_pages and
        # load_content resolve page paths THROUGH orchestration/sitemaps/<p>.txt
        # (same convention) — without it they compute FLAT paths and every write
        # to a moved page fails with "Parent path does not exist" (observed).
        if paths and not dry:
            os.makedirs("orchestration/sitemaps", exist_ok=True)
            with open(f"orchestration/sitemaps/{project}.txt", "w") as f:
                f.write("# derived from the crawl URL hierarchy by build_nav_tree\n")
                f.write("\n".join(paths) + "\n")
            print(f"  ~ persisted orchestration/sitemaps/{project}.txt")
    print(f"[build_nav_tree] {len(paths)} nested path(s) from the {src}")
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

    # ── pass 1b: place the cross-cutting CHROME singletons (tree-driven nav,
    # header, footer) into their AbsoluteAreas under /home. The content loader
    # skips chrome by design ("populated separately"); THIS is separately. Each
    # is a single node whose view reads the page tree — no own content needed. ──
    def exists_node(p):
        try:
            r = m.get(p, locale=locale)
            return not (isinstance(r, dict) and r.get("error"))
        except Exception:
            return False

    try:
        manifest = json.load(open(f"projects/{project}/workflow-output/component-manifest.json"))
    except (FileNotFoundError, ValueError):
        manifest = {}
    for c in (manifest.get("crossCutting") or []):
        nt = c.get("nodeType")
        area = c.get("area") or c.get("chrome")
        if not nt or not area or nt.endswith(":rawHtml"):
            continue
        area_path = f"{home}/{area}"
        node_path = f"{area_path}/{nt.split(':')[-1]}"
        if exists_node(node_path):
            continue
        if dry:
            print(f"[dry] place chrome {node_path} ({nt})")
            continue
        try:
            if not exists_node(area_path):
                m.create(home, "jnt:contentList", {}, name=area, locale=locale)
            m.create(area_path, nt, {}, name=nt.split(":")[-1], locale=locale)
            print(f"  + chrome {node_path} ({nt})")
            created += 1
        except Exception as e:
            print(f"  ! chrome {nt}: {str(e)[:140]}", file=sys.stderr)

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
