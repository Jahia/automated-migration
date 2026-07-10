#!/usr/bin/env python3
"""create_pages.py — DETERMINISTIC page creation from the crawl inventory.

Creates one jnt:page per crawled page under /sites/<site>/home (flat, matching
load_content._slug_to_jcr_path's fallback when no sitemap file exists), with
the source page title, the module's `basic` template, and en+fr titles (rule:
all modules ship en+fr minimum). Publishes each page. Idempotent: existing
pages are kept (title refreshed), never duplicated.

SITEMAP-AWARE (nav doctrine, 2026-07-06): when orchestration/sitemaps/
<project>.txt exists, each slug's canonical path resolves THROUGH it (same
convention as load_content._slug_to_jcr_path) — a page build_nav_tree.py moved
under its section (/home/brands/en_citadines) is found there, never recreated
flat. New pages are still created flat when the sitemap parent is absent
(fresh DB: build_nav_tree restructures afterward). --check gates on the
sitemap-resolved paths.

Usage: create_pages.py <project> <site> [--template basic] [--locale en]
       [--limit N] [--dry]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP  # noqa: E402


def sitemap_map(project):
    """leaf slug (lowercase) -> sitemap rel path; {} when no sitemap file."""
    out = {}
    try:
        for line in open(f"orchestration/sitemaps/{project}.txt"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out[line.split("/")[-1].lower()] = line
            out[line.lower()] = line
    except FileNotFoundError:
        pass
    return out


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: create_pages.py <project> <site> [--template basic] [--locale en] [--limit N] [--dry]")
    project, site = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    template = args[args.index("--template") + 1] if "--template" in args else "basic"
    locale = args[args.index("--locale") + 1] if "--locale" in args else "en"
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    dry = "--dry" in args
    check = "--check" in args

    inv_path = f"projects/{project}/workflow-output/page-inventory.json"
    inv = json.load(open(inv_path))
    pages = [p for p in inv.get("pages", []) if p.get("slug")]
    # the crawl's HOME page slug is rarely "home" (discoverasr: "en", url ==
    # siteUrl). It must map to /sites/<site>/home itself, never /home/<slug> —
    # same rule as load_content._home_slug (loader wrote /home/main while a
    # spurious empty /home/en page failed the integrity belt).
    site_url = (inv.get("siteUrl") or "").rstrip("/")
    hs = next((q["slug"] for q in inv.get("pages", [])
               if (q.get("url") or "").rstrip("/") == site_url), None)
    if hs is None and inv.get("pages"):
        hs = inv["pages"][0].get("slug")
    for q in pages:
        if q.get("slug") == hs:
            q["slug"] = "home"
    if limit:
        pages = pages[:limit]

    m = MCP(project)
    smap = sitemap_map(project)

    def page_path(slug):
        if slug == "home":
            return f"/sites/{site}/home"
        rel = smap.get(slug.lower(), slug)
        return f"/sites/{site}/home/{rel}"

    if check:
        # Gate mode (M4 live find): content.get on /home alone passes with an
        # empty home skeleton — assert the WHOLE inventory tree exists in JCR.
        missing = []
        for p in pages:
            path = page_path(p["slug"])
            try:
                m.get(path, locale=locale)
            except Exception:
                missing.append(path)
        if missing:
            print(f"FAIL: {len(missing)}/{len(pages)} inventory pages missing in JCR:",
                  file=sys.stderr)
            for path in missing[:10]:
                print(f"  - {path}", file=sys.stderr)
            sys.exit(1)
        print(f"PASS: all {len(pages)} inventory pages exist in JCR")
        return
    other = "fr" if locale != "fr" else "en"
    created = updated = published = 0
    for p in pages:
        slug, title = p["slug"], (p.get("title") or p["slug"]).strip()[:250]
        if slug == "home":
            # home exists (site init); refresh its title only
            path = f"/sites/{site}/home"
            if not dry:
                try:
                    m.update(path, {"jcr:title": title}, locale=locale)
                    m.update(path, {"jcr:title": title}, locale=other)
                    m.publish(path)
                except Exception as e:
                    print(f"  ! home title: {e}", file=sys.stderr)
            continue
        path = page_path(slug)   # sitemap-resolved (nav-moved pages found in place)
        if dry:
            print(f"  [dry] {path} <- jnt:page tpl={template} '{title[:60]}'")
            created += 1
            continue
        exists = True
        try:
            m.get(path, locale=locale)
        except Exception:
            exists = False
        flat = f"/sites/{site}/home/{slug}"
        if not exists and path != flat:
            # not at its sitemap home yet — maybe still flat (pre-nav-tree state)
            try:
                m.get(flat, locale=locale)
                exists, path = True, flat
            except Exception:
                pass
        try:
            if not exists:
                # create FLAT under /home (fresh DB) — build_nav_tree.py moves
                # pages under their sitemap sections afterward.
                path = flat
                m.create(f"/sites/{site}/home", "jnt:page",
                         {"jcr:title": title, "j:templateName": template},
                         name=slug, locale=locale)
                created += 1
            else:
                updated += 1
            m.update(path, {"jcr:title": title}, locale=other)  # rule: en+fr
            m.publish(path)
            published += 1
            print(f"  + {path} ('{title[:60]}')")
        except Exception as e:
            print(f"  ! {slug}: {e}", file=sys.stderr)
    print(f"create_pages: {created} created, {updated} existing, {published} published"
          f"{' [dry]' if dry else ''}")


if __name__ == "__main__":
    main()
