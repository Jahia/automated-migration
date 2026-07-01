#!/usr/bin/env python3
"""wire_startnodes.py — enforce the mainResource listing invariant (ETL phase,
runs AFTER load_main_resources + page creation). Two passes:

  1. WIRE — point every mainResource lsp:jcrQuery.startNode at its jnt:contentFolder.
     The listing pages carry an lsp:jcrQuery whose `type` property names the
     mainResource node type it lists (lsp:newsArticle, lsp:agendaItem). Its startNode
     (weakreference) must resolve to the jnt:contentFolder that holds those nodes —
     NOT /home (the LLM's default mis-wire), or the ISDESCENDANTNODE query scoops up
     unrelated content. Mapping: jcrQuery.type -> folder (from
     <project>.mainresource-load.json); page-path disambiguation if a type repeats.

  2. CLEAN — remove any mainResource node that lives OUTSIDE its contentFolder.
     Prior LLM runs create articles inline in page main areas (duplicates + pure
     fabrication like article-1/agenda-2). mainResource content is folder-only; any
     lsp:newsArticle/lsp:agendaItem not under a declared folder is debris and is
     removed (mark_for_deletion + publish — the sanctioned live-delete path). Skip
     with --no-clean. Gated by mainresource.sh (placement invariant).

Usage: python3 orchestration/lib/wire_startnodes.py <project> <site> [--dry] [--no-clean]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP


def load_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def clean_inline(m, project, site, folder_paths, dry):
    """Remove mainResource-type nodes that live OUTSIDE any declared contentFolder."""
    manifest = load_json(f"projects/{project}/workflow-output/component-manifest.json", {})
    mr_types = {c.get("nodeType") for c in manifest.get("components", []) if c.get("needsMainResource")}
    removed = 0
    for nt in sorted(mr_types):
        r = m.call("content.search", {"siteKey": site, "nodeType": nt, "locale": "fr", "limit": 100})
        for n in (r.get("results", []) if isinstance(r, dict) else []):
            p = n.get("path")
            if not p or any(p.startswith(fp + "/") or p == fp for fp in folder_paths):
                continue  # correctly inside a declared folder
            if dry:
                print(f"  [dry] remove misplaced {nt}: {p}"); removed += 1; continue
            try:
                m.call("content.mark_for_deletion", {"path": p})
                m.call("publication.publish", {"path": p, "languages": ["fr", "en"]})
                print(f"  removed misplaced {nt}: {p.split('/home/')[-1]}")
                removed += 1
            except Exception as e:
                print(f"  ! remove {p}: {e}", file=sys.stderr)
    return removed


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: wire_startnodes.py <project> <site> [--dry] [--no-clean]")
    project, site = sys.argv[1], sys.argv[2]
    argv = sys.argv[3:]
    dry = "--dry" in argv
    do_clean = "--no-clean" not in argv
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

    if do_clean:
        folder_paths = [f["path"] for f in mrl["folders"].values()]
        print("clean: removing mainResource nodes outside their contentFolder ...")
        removed = clean_inline(m, project, site, folder_paths, dry)
        print(f"wire_startnodes: removed {removed} misplaced mainResource node(s){' [dry]' if dry else ''}")


if __name__ == "__main__":
    main()
