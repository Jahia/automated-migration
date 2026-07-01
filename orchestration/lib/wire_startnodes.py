#!/usr/bin/env python3
"""wire_startnodes.py — point every mainResource lsp:jcrQuery.startNode at its
jnt:contentFolder (ETL phase, runs AFTER load_main_resources + page creation).

The listing pages carry an lsp:jcrQuery whose `type` property names the
mainResource node type it lists (lsp:newsArticle, lsp:agendaItem). Its startNode
(weakreference) must resolve to the jnt:contentFolder that holds those nodes —
NOT to /home (the LLM's default mis-wire), or the ISDESCENDANTNODE query scoops
up unrelated content and the listing is wrong.

Mapping: jcrQuery.type -> folder (from <project>.mainresource-load.json, which
records folder path + type per folder). If two folders share a type, disambiguate
by matching the query's page path against the folder's listingPages.

Usage: python3 orchestration/lib/wire_startnodes.py <project> <site> [--dry]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP


def load_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: wire_startnodes.py <project> <site> [--dry]")
    project, site = sys.argv[1], sys.argv[2]
    dry = "--dry" in sys.argv[3:]
    m = MCP(project)

    mrl = load_json(f"orchestration/content/{project}.mainresource-load.json")
    if not mrl or not mrl.get("folders"):
        sys.exit("wire_startnodes: no mainresource-load.json — run load_main_resources.py first")
    cfg = load_json(f"orchestration/content/{project}.mainresource.json", {})

    # type -> [folder paths]; and listingPages -> folder path (disambiguation)
    type_folders = {}
    for fname, f in mrl["folders"].items():
        type_folders.setdefault(f["type"], []).append(f["path"])
    listing_map = mrl.get("listingPages", {})  # page-url -> folder path

    # NB: content.search silently returns empty for limit > 100 — keep it <= 100.
    r = m.call("content.search", {"siteKey": site, "nodeType": "lsp:jcrQuery",
                                  "locale": "fr", "limit": 100})
    queries = r.get("results", r.get("nodes", [])) if isinstance(r, dict) else []
    wired = skipped = 0
    for q in queries:
        qpath = q.get("path")
        d = m.get(qpath)
        props = d.get("properties", {}) or {}
        qtype = props.get("type")
        folders = type_folders.get(qtype)
        if not folders:
            skipped += 1
            continue  # not a mainResource listing we manage
        if len(folders) == 1:
            target = folders[0]
        else:
            # disambiguate: match query's page path against a listingPages key
            page_path = qpath.split("/main/")[0]
            target = next((fp for lp, fp in listing_map.items()
                           if page_path.endswith(lp)), folders[0])
        if dry:
            print(f"  [dry] {qpath}\n         startNode -> {target}")
            wired += 1
            continue
        try:
            m.update(qpath, {"startNode": target})
            m.publish(qpath)
            print(f"  wired {qpath}\n         startNode -> {target}")
            wired += 1
        except Exception as e:
            print(f"  ! {qpath}: {e}", file=sys.stderr)
    print(f"\nwire_startnodes: wired {wired}, skipped {skipped} (non-mainResource){' [dry]' if dry else ''}")


if __name__ == "__main__":
    main()
