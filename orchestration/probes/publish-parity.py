#!/usr/bin/env python3
"""publish-parity.py — reference + translation integrity, asserted in EDIT.

EDIT-ONLY / NO-LIVE DOCTRINE (Julian, 2026-07-04: "aucun test en live"): the
migration process is EDIT-only; publication is a single FINAL act performed by
Julian via publish_site.sh. During the process LIVE is deliberately stale
(measured live: EDIT 1877 content nodes vs LIVE 1780) — comparing against LIVE
would fail on that expected staleness and prove nothing about the work done.
So this probe reads ONLY the EDIT workspace, NEVER LIVE, and NEVER publishes.

What it still proves, entirely in EDIT (the two failures that recur in
migrations and that are real REGARDLESS of publication state):
  1. REFERENCE INTEGRITY — every weakreference on migrated content (image / logo
     / j:linknode / j:defaultCategory / ...) resolves to a node that EXISTS
     (its `refNode` is non-null). A dangling weakref is a broken asset whether
     or not the page is published; the moment it is published it renders as a
     hole. Weakref VALUES come through the `refNode`/`value` fields, not
     `values` (which is null for single weakrefs) — the old LIVE query read
     `values` and silently checked nothing.
  2. TRANSLATION PARITY — for every requested language, content that carries a
     translated `jcr:title` in ONE language must not be MISSING it in another
     requested language within EDIT (a translation node that was never created
     — the i18n gap that later publishes as an empty locale).

The LIVE half of publish-COMPLETENESS ("everything that is in EDIT actually
reached LIVE") is not this probe's business anymore. It is verified AFTER the
single final publication by:
    orchestration/assist/publish_site.sh  (the publication itself)
    orchestration/probes/integrity.py --phase step_publish_final  (EDIT↔LIVE
        alignment once publication has happened)
Running it here, pre-publication, would only re-measure the tolerated stale LIVE.

Invoked by publish-parity.sh (passes JAHIA_URL / JAHIA_USER / JAHIA_PASS /
siteKey / langs). Exit 0 = clean, 1 = dangling references / translation gaps.
"""
import base64, json, os, sys, urllib.request

HOST = os.environ.get("JAHIA_URL", os.environ.get("JAHIA_HOST", "http://localhost:8080")).rstrip("/")
USER = os.environ.get("JAHIA_USER", "root:root")
if ":" not in USER:
    USER = f"{USER}:{os.environ.get('JAHIA_PASS', 'root')}"
SITE = sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: publish-parity.py <siteKey> [langs csv]")
LANGS = ([x for x in sys.argv[2].split(",") if x] if len(sys.argv) > 2 and sys.argv[2] else ["en"])
GQL = f"{HOST}/modules/graphql"
AUTH = "Basic " + base64.b64encode(USER.encode()).decode()


def gql(query):
    req = urllib.request.Request(
        GQL, data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "Origin": HOST, "Authorization": AUTH})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def q_nodes(sql, lang):
    """All EDIT nodes matching sql, with each property's name, single value,
    multi values, and definition type. NOTE: we deliberately do NOT request
    `refNode` here — Jahia raises `invalid identifier` when refNode is asked of
    a NON-reference property (or an empty one), which aborts the whole query.
    Reference targets are resolved in a separate nodeById pass instead."""
    d = gql(f'{{jcr(workspace:EDIT){{nodesByQuery(query:"{sql}"){{nodes{{'
            f'uuid path properties(language:"{lang}"){{name value values '
            f'definition{{requiredType}}}}}}}}}}}}')
    if d.get("errors"):
        sys.exit(f"FAIL: publish-parity GraphQL error: {json.dumps(d['errors'])[:300]}")
    return d["data"]["jcr"]["nodesByQuery"]["nodes"]


esc = lambda p: p.replace("'", "''")
SCOPE = f"isdescendantnode('/sites/{esc(SITE)}')"

# ---- 1. reference integrity in EDIT: every reference UUID resolves ----
# structural node references (startNode, j:defaultCategory, etc.) count too — a
# dangling one is a broken relationship regardless of publication.
refs = []  # (path, prop, uuid)
seen_ref_props = 0
edit = q_nodes(f"select * from [jnt:content] where {SCOPE}", LANGS[0])
for n in edit:
    for p in n.get("properties", []):
        if (p.get("definition") or {}).get("requiredType") not in ("WEAKREFERENCE", "REFERENCE"):
            continue
        vals = p.get("values") or ([p["value"]] if p.get("value") else [])
        vals = [v for v in vals if v and len(v) >= 32 and "-" in v]  # uuid-shaped
        if not vals:
            continue
        seen_ref_props += 1
        refs.extend((n["path"], p["name"], v) for v in vals)

# resolve every referenced uuid in EDIT, chunked with aliases; a uuid with no
# node behind it is a dangling reference (broken asset/link/category).
uuids = sorted({u for _, _, u in refs})
resolved = set()
for i in range(0, len(uuids), 40):
    chunk = uuids[i:i + 40]
    body = " ".join(f'a{j}:nodeById(uuid:"{u}"){{uuid}}' for j, u in enumerate(chunk))
    d = gql(f"{{jcr(workspace:EDIT){{{body}}}}}")
    data = (d.get("data") or {}).get("jcr") or {}
    for j, u in enumerate(chunk):
        if data.get(f"a{j}"):
            resolved.add(u)
broken = [(pa, pr, u) for (pa, pr, u) in refs if u not in resolved]

# ---- 2. translation parity WITHIN EDIT across requested languages ----
# For each translatable content node, if it carries a jcr:title in ANY requested
# language it must carry one in EVERY requested language (a missing translation
# node = the locale that would publish empty).
trans_gaps = []
if len(LANGS) > 1:
    # collect the union of nodes that have a title in at least one lang
    per_lang_titles = {}  # lang -> {uuid: bool has title}
    node_paths = {}
    for lang in LANGS:
        titled = {}
        for n in q_nodes(f"select * from [jnt:content] where {SCOPE}", lang):
            node_paths[n["uuid"]] = n["path"]
            t = next((p for p in n.get("properties", []) if p["name"] == "jcr:title"), None)
            titled[n["uuid"]] = bool(t and t.get("value"))
        per_lang_titles[lang] = titled
    all_uuids = set().union(*[set(d) for d in per_lang_titles.values()])
    for u in all_uuids:
        present = [lang for lang in LANGS if per_lang_titles.get(lang, {}).get(u)]
        if present and len(present) < len(LANGS):
            missing = [lang for lang in LANGS if lang not in present]
            trans_gaps.append((node_paths.get(u, u), ",".join(missing)))

# ---- report ----
print(json.dumps({
    "workspace": "EDIT",
    "edit_content_nodes": len(edit),
    "reference_props_checked": seen_ref_props,
    "langs": LANGS,
    "broken_refs": [{"node": p, "prop": pr, "unresolved_uuid": u} for p, pr, u in broken][:30],
    "translation_gaps": [{"node": p, "missing_lang": l} for p, l in trans_gaps][:30],
}, indent=1, ensure_ascii=False))

if broken or trans_gaps:
    print(f"FAIL: publish-parity — {len(broken)} dangling reference(s) + "
          f"{len(trans_gaps)} translation gap(s) in EDIT", file=sys.stderr)
    sys.exit(1)
print("PASS: publish-parity — all references resolve in EDIT; no translation gaps "
      "(LIVE completeness verified post-publication by publish_site.sh + "
      "integrity --phase step_publish_final)")
