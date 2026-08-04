#!/usr/bin/env python3
"""entity-payload.py — prove the ENTITY content BEFORE loading it.

Every other entity gate fires too late or too shallow:
  * entity-coverage   — are the URLs accounted for? (a ledger question)
  * mainresource.sh   — did folders get created with >=1 node? (post-load)
  * mainresource-model — is the CND a container, is a body flattened? (shape)

None of them answers the question that decides whether the migration is worth
publishing: **does each entity detail actually yield a title, a date and body
bands from the captured mirror?** A detail whose extraction comes out empty
becomes a titleless node with no content, and today that is only discoverable
after the load — by looking.

So this runs the REAL producer (load_main_resources.article_core + entity_bands)
over every declared entity detail in the mirror and fails on the ones that would
load hollow. Same code path as the loader, so a pass here means the loader has
something to write; a fail names the slug and what is missing.

FAILS when:
  1. a declared entity folder resolves to ZERO mirror pages (nothing to load),
  2. any entity would load with no title,
  3. any entity would load with no body bands AND no standfirst,
  4. more than `--max-dateless` of a dated family lack a date (the field map is
     probably wrong for that family, not the pages).

Usage: entity-payload.py <project> [--max-dateless 0.25] [--report]
"""
import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "lib")


def load_producer():
    sys.path.insert(0, LIB)
    spec = importlib.util.spec_from_file_location(
        "lmr", os.path.join(LIB, "load_main_resources.py"))
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--max-dateless", type=float, default=0.25)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    p = a.project
    pp = f"projects/{p}"
    mirror = f"{pp}/workflow-output/local-mirror"
    mrp = f"orchestration/content/{p}.mainresource.json"
    if not os.path.exists(mrp):
        print(f"PASS entity-payload: no entity map for {p} — nothing declared")
        return
    cfg = json.load(open(mrp))
    folders = cfg.get("folders") or {}
    if not folders:
        print("PASS entity-payload: entity map declares no folders")
        return
    if not os.path.isdir(mirror):
        sys.exit(f"FAIL entity-payload: no scoped mirror at {mirror}")

    M = load_producer()
    slugs = sorted(f[:-5] for f in os.listdir(mirror) if f.endswith(".html"))
    fails, rows = [], []
    DATED = {"date", "startDate", "publishDate"}

    for fname, fcfg in folders.items():
        prefixes = [x.strip("/") for x in (fcfg.get("urlPrefixes") or [])]
        mine = [s for s in slugs
                if any(s.replace("_", "/").startswith(pre + "/") for pre in prefixes)]
        if not mine:
            fails.append(f"folder '{fname}' ({fcfg.get('type')}) resolves to ZERO "
                         f"mirror page(s) for prefixes {prefixes} — nothing to load")
            continue
        wants_date = bool(DATED & set((fcfg.get("fieldMap") or {}).keys()))
        no_title, no_body, no_date = [], [], []
        for s in mine:
            try:
                title, date_iso, hero, main_el = M.article_core(f"{mirror}/{s}.html")
                ns = (fcfg.get("type") or "x:y").split(":")[0]
                bands, _mode = M.entity_bands(
                    main_el, ns, lambda k: f"{ns}:{M._arch.node_local(k)}")
            except Exception as e:                                  # noqa: BLE001
                fails.append(f"{fname}/{s}: extraction RAISED ({str(e)[:80]})")
                continue
            text = sum(len(re.sub(r"<[^>]+>", " ", b["body"] or "")) for b in bands)
            if not (title or "").strip():
                no_title.append(s)
            if not bands or text < 40:
                no_body.append(s)
            if wants_date and not date_iso:
                no_date.append(s)
        rows.append((fname, len(mine), len(no_title), len(no_body), len(no_date)))
        if no_title:
            fails.append(f"folder '{fname}': {len(no_title)} of {len(mine)} entity/"
                         f"entities would load with NO TITLE ("
                         + ", ".join(no_title[:4]) + ")")
        if no_body:
            fails.append(f"folder '{fname}': {len(no_body)} of {len(mine)} would load "
                         f"with NO BODY ({', '.join(no_body[:4])})")
        if wants_date and no_date and len(no_date) / len(mine) > a.max_dateless:
            fails.append(f"folder '{fname}': {len(no_date)} of {len(mine)} lack a DATE "
                         f"(> {a.max_dateless:.0%}) — the fieldMap date source is "
                         f"probably wrong for this family, not the pages")

    if a.report or fails:
        print("entity payload (folder / pages / no-title / no-body / no-date):")
        for r in rows:
            print(f"   {r[0]:<22} {r[1]:>4} {r[2]:>9} {r[3]:>8} {r[4]:>8}")
    if fails:
        print(f"FAIL entity-payload [{p}] — {len(fails)} finding(s)")
        for f in fails[:10]:
            print(f"  - {f}")
        print("  Fix: the entity would load hollow. Check the family's fieldMap, or "
              "whether its detail pages were captured at all.")
        sys.exit(1)
    tot = sum(r[1] for r in rows)
    print(f"PASS entity-payload: {tot} entity detail(s) across {len(rows)} folder(s) "
          f"all yield a title and body bands from the mirror")


if __name__ == "__main__":
    main()
