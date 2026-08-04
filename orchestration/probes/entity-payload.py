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
from collections import Counter

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
    ap.add_argument("--config-only", action="store_true",
                    help="run only the checks that read the entity map, not the mirror "
                         "(seconds instead of minutes; used to test this gate and to "
                         "fail a bad map before any page work happens)")
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

    M = None if a.config_only else load_producer()
    slugs = sorted(f[:-5] for f in os.listdir(mirror) if f.endswith(".html"))
    fails, rows = [], []
    DATED = {"date", "startDate", "publishDate"}

    # FOLDERS SHARING A TYPE MUST BE TELLABLE APART (2026-08-04). The catalogue's three
    # axes were consolidated into one sdp:directoryEntry precisely because their field
    # surfaces are identical — which is right, but then something has to carry the axis.
    # Nothing did: no folder set the `kind` choicelist the type was approved with, so 77
    # entries would have loaded indistinguishable and every kind-filtered listing would
    # return nothing. A shared type with no distinguishing fixedProp is a modelling hole,
    # visible in the config alone — no need to read a single page to know it.
    # Only when the TYPE ITSELF declares a discriminator. Five folders share
    # sdp:event and that is perfectly fine — an agenda entry and a programme entry are
    # told apart by their folder, which is what jcrQuery.startNode selects on. But
    # sdp:directoryEntry was approved with a `kind` choicelist (exposant|marque|produit)
    # precisely because the catalogue's three axes are one type, and then no folder set
    # it. A first version of this check compared fixedProps across every shared type and
    # cried wolf on event and newsArticle; the archetype's own discriminator is the
    # signal, not the sharing.
    sys.path.insert(0, LIB)
    try:
        import archetypes as ARCH
    except ImportError:
        ARCH = None

    def _discriminator(nt):
        if ARCH is None:
            return None
        local = (nt or "").split(":")[-1]
        for k, v in ARCH.ARCHETYPES.items():
            if ARCH.node_local(k) == local:
                return ((v.get("layout") or {}).get("name")
                        if (v.get("layout") or {}).get("values") else None)
        return None

    by_type = {}
    for fname, fcfg in folders.items():
        by_type.setdefault(fcfg.get("type"), []).append((fname, fcfg))
    for nt, group in by_type.items():
        disc = _discriminator(nt)
        if not disc or len(group) < 2:
            continue
        missing = [g[0] for g in group if not (g[1].get("fixedProps") or {}).get(disc)]
        if missing:
            fails.append(f"type '{nt}' declares the discriminator '{disc}' and "
                         f"{len(group)} folders share it, but {len(missing)} set no "
                         f"value ({', '.join(missing)}) — every entry would load "
                         f"indistinguishable and a {disc}-filtered listing returns "
                         f"nothing")
        vals = [(g[1].get("fixedProps") or {}).get(disc) for g in group]
        if len(set(v for v in vals if v)) < len([v for v in vals if v]):
            fails.append(f"type '{nt}': folders repeat the same '{disc}' value "
                         f"({', '.join(str(v) for v in vals)}) — the discriminator does "
                         f"not discriminate")

    if a.config_only:
        if fails:
            print(f"FAIL entity-payload [{p}] (config) — {len(fails)} finding(s)")
            for f in fails:
                print(f"  - {f}")
            sys.exit(1)
        print(f"PASS entity-payload (config): {len(folders)} folder(s), "
              f"{len(by_type)} type(s), each shared type distinguishable")
        return

    for fname, fcfg in folders.items():
        prefixes = [x.strip("/") for x in (fcfg.get("urlPrefixes") or [])]
        mine = [s for s in slugs
                if any(s.replace("_", "/").startswith(pre + "/") for pre in prefixes)]
        if not mine:
            fails.append(f"folder '{fname}' ({fcfg.get('type')}) resolves to ZERO "
                         f"mirror page(s) for prefixes {prefixes} — nothing to load")
            continue
        wants_date = bool(DATED & set((fcfg.get("fieldMap") or {}).keys()))
        no_title, no_body, no_date, thin, flat = [], [], [], [], []
        titles = []
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
            titles.append((title or "").strip())
            if not (title or "").strip():
                no_title.append(s)
            if not bands or text < 40:
                no_body.append(s)
            if wants_date and not date_iso:
                no_date.append(s)

            # COVERAGE, against the page's own text (2026-08-04). A `>= 40 chars`
            # floor passed every programme event on a body of TAB LABELS — "Sessions
            # Description Thematiques Types" — 227 of the region's 2595 chars, because
            # the band boundary took two <section>s that held the labels and not the
            # panels. Any floor would have passed it; only the ratio to what the page
            # actually says exposes it. Reference-derived, so there is no threshold to
            # tune: a short page needs little, a long page must be mostly carried over.
            own = len(re.sub(r"\s+", " ", main_el.get_text(" ", strip=True)))
            if own >= 400 and text / max(own, 1) < 0.6:
                thin.append((s, text, own))
            # and a long body that came through as ONE band is the flat richtext the
            # entity decomposition exists to prevent: every in-body image and embed
            # is frozen out of the editor's reach inside it.
            if own >= 800 and len(bands) <= 1:
                flat.append((s, own))
        rows.append((fname, len(mine), len(no_title), len(no_body), len(no_date),
                     len(thin), len(flat)))
        if no_title:
            fails.append(f"folder '{fname}': {len(no_title)} of {len(mine)} entity/"
                         f"entities would load with NO TITLE ("
                         + ", ".join(no_title[:4]) + ")")
        if no_body:
            fails.append(f"folder '{fname}': {len(no_body)} of {len(mine)} would load "
                         f"with NO BODY ({', '.join(no_body[:4])})")
        # DISTINCT ENTITIES HAVE DISTINCT NAMES (2026-08-04). A catalogue detail
        # renders inside its listing template, so the first h1 belongs to the LISTING:
        # every exhibitor, brand and product extracted as "LISTE DES EXPOSANTS" and the
        # folder would have held N identically-named nodes — each with a title, so the
        # no-title check passed all of them. Mass duplication is the signature of a
        # template heading leaking in, and it needs no threshold to tune: two events
        # can share a name, a whole folder cannot.
        seen = Counter(t for t in titles if t)
        for t, n in seen.most_common(1):
            if n >= 3 and n / len(mine) > 0.3:
                fails.append(f"folder '{fname}': {n} of {len(mine)} entities would load "
                             f"with the SAME title ({t[:44]!r}) — that is a template "
                             f"heading, not each entity's own name")
        if thin and len(thin) / len(mine) > 0.25:
            ex = "; ".join(f"{s2} ({t}/{o} chars)" for s2, t, o in thin[:3])
            fails.append(f"folder '{fname}': {len(thin)} of {len(mine)} would load a "
                         f"body carrying < 60% of what the page says ({ex}) — the band "
                         f"boundary is not accounting for the content")
        if flat:
            ex = "; ".join(f"{s2} ({o} chars)" for s2, o in flat[:3])
            fails.append(f"folder '{fname}': {len(flat)} of {len(mine)} would load as a "
                         f"SINGLE band over a long body ({ex}) — that is one flat "
                         f"richtext; its images and embeds are unreachable to editors")
        if wants_date and no_date and len(no_date) / len(mine) > a.max_dateless:
            fails.append(f"folder '{fname}': {len(no_date)} of {len(mine)} lack a DATE "
                         f"(> {a.max_dateless:.0%}) — the fieldMap date source is "
                         f"probably wrong for this family, not the pages")

    if a.report or fails:
        print("entity payload (folder / pages / no-title / no-body / no-date / "
              "thin / flat):")
        for r in rows:
            print(f"   {r[0]:<22} {r[1]:>4} {r[2]:>9} {r[3]:>8} {r[4]:>8} "
                  f"{r[5]:>6} {r[6]:>5}")
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
