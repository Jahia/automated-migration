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
    # clean menu labels (extract_nav.py writes them from the SOURCE's nav —
    # "Document Services", not the page's SEO <title>); merged over NAV_TITLES
    labels = {}
    try:
        labels = json.load(open(f"orchestration/sitemaps/{project}.labels.json"))
    except (FileNotFoundError, ValueError):
        pass
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
    retitled = 0
    for rel in paths:
        target = f"{home}/{rel}"
        leaf = rel.split("/")[-1]
        parent = f"{home}/{'/'.join(rel.split('/')[:-1])}".rstrip("/")

        def title_for(lf):
            t = labels.get(lf) or NAV_TITLES.get(lf, {}).get(locale)
            return t or lf.replace("-", " ").title()

        if exists(target):
            # already in place: still align its title with the MENU label (the
            # crawled page carries its SEO <title> — "Health Insurance Singapore
            # | HSBC Life Protection | SingPost" is not a menu label)
            if leaf in labels and not dry:
                try:
                    m.update(target, {"jcr:title": labels[leaf]}, locale=locale)
                    retitled += 1
                except Exception as e:
                    print(f"  ! retitle {leaf}: {str(e)[:120]}", file=sys.stderr)
            continue
        flat = f"{home}/{leaf}"
        if not exists(flat):
            # the page may have been NESTED by a previous sitemap run — locate
            # it anywhere under home by node name before fabricating a stub
            try:
                r = m.gql('query { jcr(workspace: EDIT) { nodesByQuery(query: '
                          '"SELECT * FROM [jnt:page] AS p WHERE ISDESCENDANTNODE(p,'
                          "'%s') AND NAME(p)='%s'\", queryLanguage: SQL2, limit: 2) "
                          '{ nodes { path } } } }' % (home, leaf))
                found = [n["path"] for n in ((r or {}).get("jcr", {})
                                             .get("nodesByQuery", {}) or {}).get("nodes", [])]
            except Exception:
                found = []
            if found:
                flat = found[0]
        # guard: never move a page under its own subtree (menu quirk like
        # receiving/receiving — the L1 section and an L2 page share the slug)
        cycle = parent == flat or parent.startswith(flat + "/")
        if exists(flat) and flat != target and not cycle:
            # crawled page sitting flat under /home -> MOVE under its section
            if dry:
                print(f"[dry] move {flat} -> {parent}/")
            else:
                r = m.gql('mutation { jcr(workspace: EDIT) { moveNode(pathOrId: "%s", '
                          'destParentPathOrId: "%s") { node { path } } } }'
                          % (flat, parent))
                if isinstance(r, dict) and r.get("errors"):
                    print(f"  ! move {leaf}: {str(r['errors'])[:140]}", file=sys.stderr)
                    continue
                print(f"  ~ moved {leaf} -> {parent}/")
                if leaf in labels:
                    try:
                        m.update(target, {"jcr:title": labels[leaf]}, locale=locale)
                        retitled += 1
                    except Exception:
                        pass
            moved += 1
            continue
        # new SECTION page (menu category or menu target the crawl never fetched)
        t_loc = title_for(leaf)
        t_oth = NAV_TITLES.get(leaf, {}).get(other) or t_loc
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
    if retitled:
        print(f"  ~ retitled {retitled} page(s) with menu labels")

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

    # ── pass 1c: pages that exist but are NOT in the menu IA (audience/footer/
    # utility pages the crawl fetched) — flag them {mixns}:hideFromNav so the
    # tree-driven nav skips them. They stay URL-reachable and jContent-editable;
    # an editor removes the mixin to surface one in the menu. ──
    mixns_prefix = None
    try:
        mf = json.load(open(f"projects/{project}/workflow-output/component-manifest.json"))
        if mf.get("model") == "archetype":
            mixns_prefix = mf.get("mixns")
    except (FileNotFoundError, ValueError):
        pass
    # ── MULTI-SECTION IA (2026-07-20): section roots (from section-navs.json)
    # are switcher targets, NEVER L1 menu entries of another section — they
    # keep hideFromNav, leave the L1 reorder, and get sectionRoot+sectionLabel.
    # Root slug = the section's shared URL prefix; a prefixless section (the
    # source's default audience, PERSONAL) is home itself.
    section_roots = {}   # root slug ('' == home) -> section label
    try:
        sn = json.load(open(f"projects/{project}/workflow-output/section-navs.json"))
        for label, items in sn.items():
            urls = []
            def _cu(its):
                for it in its or []:
                    h = (it.get("href") or "").split("#")[0].split("?")[0]
                    if h.startswith("/") and h != "/":
                        urls.append(h.strip("/"))
                    _cu(it.get("subMenu"))
            _cu(items)
            first = {u.split("/")[0] for u in urls}
            section_roots["" if len(first) != 1 else first.pop()] = label
    except (FileNotFoundError, ValueError):
        pass

    if mixns_prefix and not dry:
        in_menu = {p.split("/")[0] for p in paths} - {r for r in section_roots if r}
        r = m.gql('query { jcr(workspace: EDIT) { nodeByPath(path: "%s") '
                  '{ children(typesFilter: {types: ["jnt:page"]}) { nodes { name } } } } }'
                  % home)
        kids = [n["name"] for n in ((r or {}).get("jcr", {})
                                    .get("nodeByPath", {}) or {}).get("children", {}).get("nodes", [])]
        for name in kids:
            if name in in_menu:
                continue
            try:
                m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s/%s") '
                      '{ addMixins(mixins: ["%s:hideFromNav"]) } } }'
                      % (home, name, mixns_prefix))
                print(f"  ~ hidden from nav: {name}")
            except Exception as e:
                print(f"  ! hideFromNav {name}: {str(e)[:120]}", file=sys.stderr)

    # ── section-root stamping (sectionRoot mixin + editable sectionLabel) ──
    if mixns_prefix and section_roots and not dry:
        for root, label in section_roots.items():
            path = home if not root else f"{home}/{root}"
            try:
                m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s") '
                      '{ addMixins(mixins: ["%s:sectionRoot"]) } } }'
                      % (path, mixns_prefix))
                m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s") '
                      '{ mutateProperty(name: "sectionLabel") '
                      '{ setValue(language: "%s", value: %s) } } } }'
                      % (path, locale, json.dumps(label.title() if label.isupper() else label)))
                print(f"  ~ section root: {root or '(home)'} -> {label}")
            except Exception as e:
                print(f"  ! sectionRoot {root}: {str(e)[:120]}", file=sys.stderr)

    # ── pass 2: L1 order under /home == sitemap L1 order ──
    l1 = [p for p in paths if "/" not in p and p.split("/")[0] not in section_roots]
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
