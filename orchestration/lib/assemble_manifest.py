#!/usr/bin/env python3
"""assemble_manifest.py — Deterministic manifest assembler (lever 1 + 2 + 3).

The LLM now outputs ONLY a GROUPING (a partition of the deterministic content
candidate ids) plus a few enum/bool decisions. This script turns that grouping
into the final Jahia component-manifest — computing every NAME deterministically
from the candidate roles, so naming variance across LLM runs is 0 by construction.

Levers:
  1. nodeType / fields / child types are COMPUTED here, never chosen by the LLM.
  2. no-new-types + full-coverage partition gate: any group member that is not a
     known content-candidate id (hallucination) or any uncovered candidate FAILS.
  3. --consensus fuses N grouping files by majority co-membership before assembling.

Cross-cutting components are taken deterministically from the candidate set
(crossCutting[]), never from the LLM.

Usage:
  # single grouping -> manifest (also runs the partition gate)
  python3 assemble_manifest.py <candidates.json> --group <grouping.json> --out <manifest.json>
  # consensus over many groupings -> manifest
  python3 assemble_manifest.py <candidates.json> --consensus <dir/group-*.json ...> --out <manifest.json>
"""
import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations


def camel(role):
    parts = re.split(r"[^a-zA-Z0-9]+", role or "")
    parts = [p for p in parts if p]
    if not parts:
        return "component"
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def title_case(role):
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", role or "") if p]
    return " ".join(p.capitalize() for p in parts) or "Component"


# ── Naming-quality gate ───────────────────────────────────────────
# The partition gate proves the model is STRUCTURALLY sound (no hallucination /
# omission). It says nothing about whether an editor can READ the type names.
# This gate flags editor-hostile names so a green structural gate can't hide an
# unusable model (contentful: 21/21 hashed; liferay: lfr:div at freq 66).

# bare structural HTML tags that carry no editorial meaning as a content type
# (chrome tags header/footer/nav are legitimate roles and excluded)
_BARE_TAG = {"div", "span", "section", "article", "aside", "ul", "ol", "li",
             "p", "a", "figure", "main", "container", "component", "wrapper"}
# leaked framework/layout class fragments that should never name a content type
_LEAKED_RE = re.compile(r"(?i)(^|[A-Z])(col(span|start|end)?\d|lfr|portlet|clay|"
                        r"layoutstructure|swiper|coh|ssa|atb|fragment)")
# CSS-module build hashes (9Pqm4, Peo73, oT7oZ, V4DoP) are dense runs: a 5-8 char
# window where digits+uppercase OUTNUMBER-OR-EQUAL lowercase, with ≥1 of each of
# {digit, lowercase}. A camelCase word ('partners2List', 'callToActionCard') has a
# low symbol density (mostly lowercase) in EVERY 5-window, so it never matches —
# which is what defeats shape-detection without this density test. Primary defense
# is clean_token stripping __hash at the source; this is the leaked-hash safety net.
def _looks_hash(name):
    n = len(name)
    for size in range(5, 9):
        for i in range(0, n - size + 1):
            w = name[i:i + size]
            if not w.isalnum():
                continue
            d = sum(c.isdigit() for c in w)
            u = sum(c.isupper() for c in w)
            l = sum(c.islower() for c in w)
            if d >= 1 and l >= 1 and (d + u) >= l:
                return w
    return None


def naming_violations(manifest):
    """Return [{nodeType, reason}] for editor-hostile type names in the manifest.
    Checked on the local (post-namespace) name."""
    out = []
    seen = set()
    for c in manifest.get("components", []) + manifest.get("crossCutting", []):
        nt = c.get("nodeType", "")
        if nt in seen:
            continue
        seen.add(nt)
        local = nt.split(":", 1)[-1]
        low = local.lower()
        hash_run = _looks_hash(local)
        reason = None
        if low in _BARE_TAG:
            reason = f"bare structural tag '{local}' — no editorial meaning"
        elif hash_run:
            reason = f"leaked CSS-module build hash '{hash_run}' in '{local}'"
        elif _LEAKED_RE.search(local):
            reason = f"leaked layout/framework class fragment in '{local}'"
        if reason:
            out.append({"nodeType": nt, "reason": reason})
    return out


def _name_violation(local):
    """Reason a LOCAL type name is editor-hostile, or None. Same rules as
    naming_violations, factored out for the sanitizer."""
    low = local.lower()
    if low in _BARE_TAG:
        return f"bare structural tag '{local}'"
    h = _looks_hash(local)
    if h:
        return f"leaked CSS-module build hash '{h}'"
    if _LEAKED_RE.search(local):
        return f"leaked layout/framework class fragment"
    return None


def _shape_name(fields):
    """A clean, deterministic type name from a component's field shape — used to
    replace a leaked CSS-hash / framework-class type name. Editor-readable and
    stable (same shape → same base name; the caller disambiguates collisions)."""
    names = {f.get("name") for f in (fields or [])}
    has_img = "image" in names
    has_txt = bool(names & {"body", "text"})
    has_title = "title" in names
    has_link = "j:linkType" in names
    if has_img and (has_txt or has_title):
        return "MediaSection"
    if has_title and has_txt:
        return "TextSection"
    if has_link and not has_txt:
        return "CtaSection"
    if has_title:
        return "HeadingSection"
    return "ContentSection"


def sanitize_type_names(manifest, ns="ns"):
    """Rewrite any editor-hostile type name (leaked CSS-module hash, framework
    class fragment, bare tag) to a clean shape-derived name, and propagate the
    rename through EVERY reference: component/crossCutting nodeType+name, child
    types, template mainResourceType, and instanceTypeMap values. Deterministic
    and order-stable — grouping is non-deterministic (LLM), so this is the belt
    that guarantees editor-readable, field-mapped types regardless of what the
    grouping pass named them. Returns the list of {from,to,reason} renames."""
    comps = manifest.get("components", [])
    xcut = manifest.get("crossCutting", [])
    used_local = set()
    for c in comps + xcut:
        used_local.add(c.get("nodeType", "").split(":", 1)[-1])
        ct = c.get("childType")
        if ct:
            used_local.add(ct.get("nodeType", "").split(":", 1)[-1])

    renames = {}          # old full nodeType -> new full nodeType
    rename_log = []

    def _fresh(base):
        cand = base
        i = 2
        while cand in used_local:
            cand = f"{base}{i}"
            i += 1
        used_local.add(cand)
        return cand

    def _maybe(entry, fields):
        nt = entry.get("nodeType", "")
        local = nt.split(":", 1)[-1]
        reason = _name_violation(local)
        if not reason:
            return
        new_local = _fresh(_shape_name(fields))
        prefix = nt.split(":", 1)[0] if ":" in nt else ns
        new_nt = f"{prefix}:{new_local}"
        renames[nt] = new_nt
        rename_log.append({"from": nt, "to": new_nt, "reason": reason})
        entry["nodeType"] = new_nt
        if "name" in entry:
            entry["name"] = title_case(new_local)

    for c in comps:
        _maybe(c, c.get("fields"))
        ct = c.get("childType")
        if ct:
            _maybe(ct, ct.get("fields"))
    for c in xcut:
        _maybe(c, c.get("fields"))

    if renames:
        itm = manifest.get("instanceTypeMap") or {}
        for role, nt in list(itm.items()):
            if nt in renames:
                itm[role] = renames[nt]
        for t in manifest.get("templates", []):
            if isinstance(t, dict) and t.get("mainResourceType") in renames:
                t["mainResourceType"] = renames[t["mainResourceType"]]
    return rename_log


FIELD_MAP = {
    "title:string": {"name": "title", "type": "string", "i18n": True, "mandatory": True},
    "text:string": {"name": "text", "type": "string, richtext", "i18n": True, "mandatory": False},
    "body:richtext": {"name": "body", "type": "string, richtext", "i18n": True, "mandatory": False},
    "image:weakref": {"name": "image", "type": "weakreference, picker[type='image']", "i18n": False, "mandatory": False},
    "images:weakref[]": {"name": "image", "type": "weakreference, picker[type='image']", "i18n": False, "mandatory": False},
    "link:linkType": {"name": "j:linkType", "type": "string, choicelist[linkTypeInitializer]", "i18n": False, "mandatory": False},
    "links:linkType[]": {"name": "j:linkType", "type": "string, choicelist[linkTypeInitializer]", "i18n": False, "mandatory": False},
}


def fields_from_shape(shape):
    out, seen = [], set()
    for tok in shape or []:
        f = FIELD_MAP.get(tok)
        if f and f["name"] not in seen:
            out.append(dict(f))
            seen.add(f["name"])
    return out


def load(p):
    return json.load(open(p))


# ── consensus: majority co-membership -> connected components ──

def consensus_groups(content_ids, grouping_files):
    partitions = []
    for gf in grouping_files:
        g = load(gf)
        idset = []
        for grp in g.get("groups", []):
            members = [m for m in grp.get("members", []) if m in content_ids]
            if members:
                idset.append(set(members))
        partitions.append(idset)

    # count co-membership per pair
    co = Counter()
    present = Counter()
    for part in partitions:
        flat = set().union(*part) if part else set()
        for a, b in combinations(sorted(content_ids), 2):
            if a in flat and b in flat:
                present[(a, b)] += 1
                if any(a in s and b in s for s in part):
                    co[(a, b)] += 1

    # union-find on majority edges
    parent = {i: i for i in content_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    n = len(partitions)
    for (a, b), seen in present.items():
        if seen and co[(a, b)] >= (seen / 2.0) and co[(a, b)] * 2 > seen:
            union(a, b)
    # (strict majority: co > seen/2)

    comps = defaultdict(list)
    for i in content_ids:
        comps[find(i)].append(i)
    groups = [sorted(v) for v in comps.values()]

    # aggregate group-level decisions by majority across runs
    def modal_decisions(members):
        mset = set(members)
        containers = 0
        mainres = 0
        layout_votes = Counter()
        views_votes = Counter()
        total = 0
        for gf in grouping_files:
            g = load(gf)
            for grp in g.get("groups", []):
                gm = set(m for m in grp.get("members", []) if m in content_ids)
                if gm & mset:
                    total += 1
                    if grp.get("kind") == "container":
                        containers += 1
                    if grp.get("needsMainResource"):
                        mainres += 1
                    lp = grp.get("layoutProperty")
                    if isinstance(lp, dict) and lp.get("name"):
                        layout_votes[lp["name"]] += 1
                    for v in grp.get("views", []) or []:
                        if isinstance(v, dict) and v.get("name"):
                            views_votes[v["name"]] += 1
        return {
            "container": total and containers * 2 > total,
            "mainResource": total and mainres * 2 > total,
            "layoutName": layout_votes.most_common(1)[0][0] if layout_votes else None,
            "views": [v for v, _ in views_votes.most_common()] or ["default"],
        }

    return groups, modal_decisions


def single_groups(content_ids, grouping_file):
    g = load(grouping_file)
    groups, raw = [], []
    for grp in g.get("groups", []):
        members = [m for m in grp.get("members", []) if m in content_ids]
        if not members:
            continue
        groups.append(sorted(members))
        lp = grp.get("layoutProperty")
        raw.append((set(members), {
            "container": grp.get("kind") == "container",
            "mainResource": bool(grp.get("needsMainResource")),
            "layoutName": lp.get("name") if isinstance(lp, dict) else None,
            "layoutOptions": lp.get("options") if isinstance(lp, dict) else None,
            "views": [v.get("name") for v in (grp.get("views") or []) if isinstance(v, dict)] or ["default"],
        }))

    def decide(members):
        # find the original group with the largest overlap (robust to sanitizer splits)
        ms = set(members)
        best, bestn = {}, 0
        for orig, dec in raw:
            n = len(ms & orig)
            if n > bestn:
                bestn, best = n, dec
        return best

    return groups, decide, g.get("templates", [])


def _role_tokens(role):
    return set(t for t in re.split(r"[^a-zA-Z0-9]+", (role or "").lower()) if len(t) > 2)


def _compatible(a, b):
    """Two candidate members belong in the same Jahia type only if their editable
    shapes are compatible — kills LLM grab-bags that merge incompatible shapes."""
    sa, sb = set(a["dataShape"]), set(b["dataShape"])
    ca, cb = set(a.get("childShape") or []), set(b.get("childShape") or [])
    role_overlap = bool(_role_tokens(a["role"]) & _role_tokens(b["role"]))

    if not sa and not sb:
        # both empty own-shape: identity is the child items or role kinship
        return bool(ca and cb and (ca & cb)) or role_overlap
    if bool(sa) != bool(sb):
        # one empty own-shape, one not: only same-family (shared role token) merges
        return role_overlap
    # both non-empty own-shape: compatible if one subsumes the other or they overlap
    return sa <= sb or sb <= sa or bool(sa & sb)


def sanitize_groups(groups, by_id):
    """Split any LLM group whose members are not pairwise shape-compatible into
    its compatibility clusters (union-find). Deterministic anti-grab-bag guard."""
    out = []
    for members in groups:
        recs = [by_id[m] for m in members if m in by_id]
        if len(recs) <= 1:
            out.append(members)
            continue
        parent = {m: m for m in members if m in by_id}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        ids = [m for m in members if m in by_id]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if _compatible(by_id[ids[i]], by_id[ids[j]]):
                    parent[find(ids[i])] = find(ids[j])
        clusters = defaultdict(list)
        for m in ids:
            clusters[find(m)].append(m)
        for cl in clusters.values():
            out.append(sorted(cl))
    return out


def isolate_main_resources(groups, candidates):
    """Deterministic lever: a detected mainResource entity role becomes its OWN
    type, even if the LLM (or the shape sanitizer) merged it into another group.
    A detail page renders its entity node, so the entity must not be diluted into
    a grab-bag (e.g. 'article' merged with image-containers on a shared hero img)."""
    entity_roles = {dt["entityRole"] for dt in candidates.get("detailTemplates", []) or []}
    if not entity_roles:
        return groups
    role_by_id = {c["candidateId"]: c["role"] for c in candidates["components"]}
    entity_ids = {cid for cid, role in role_by_id.items() if role in entity_roles}
    out = []
    for g in groups:
        ents = [m for m in g if m in entity_ids]
        rest = [m for m in g if m not in entity_ids]
        if ents and (rest or len(ents) > 1):
            out.extend([e] for e in ents)     # each entity → its own singleton type
            if rest:
                out.append(rest)
        else:
            out.append(g)
    return out


def assemble(candidates, groups, decide, templates, ns="ns"):
    by_id = {c["candidateId"]: c for c in candidates["components"]}
    groups = sanitize_groups(groups, by_id)   # deterministic anti-grab-bag split
    groups = isolate_main_resources(groups, candidates)  # entity gets its own type

    # Agnostic (no site-specific role names): a member is a poor NAME source if it
    # is a synthesized structural placeholder OR carries no editable data of its own.
    SYNTH = {"generic-container", "div"}

    def generic(c):
        return c["role"] in SYNTH or not c.get("dataShape")

    def lead(members):
        ms = [by_id[m] for m in members if m in by_id]
        # prefer a member with real data + meaningful role; then frequency, coverage
        return max(ms, key=lambda c: (0 if generic(c) else 1,
                                      c["frequency"], c["pageCount"], c["role"]))

    components = []
    for members in sorted(groups, key=lambda g: -sum(by_id[m]["frequency"] for m in g if m in by_id)):
        ms = [by_id[m] for m in members if m in by_id]
        if not ms:
            continue
        ld = lead(members)
        node = f"{ns}:{camel(ld['role'])}"
        # union of dominant shapes
        shape = sorted(set().union(*[set(c["dataShape"]) for c in ms]))
        fields = fields_from_shape(shape)
        is_container = any(c["isContainer"] for c in ms)
        # layout property from variant tokens or LLM decision
        variants = sorted(set().union(*[set(c.get("variantTokens", [])) for c in ms]))
        d = decide(members) if callable(decide) else decide.get(tuple(sorted(members)), {})
        layout = None
        if d.get("layoutName") and (len(variants) >= 2 or d.get("layoutOptions")):
            layout = {"name": camel(d["layoutName"]),
                      "options": d.get("layoutOptions") or variants}
        elif len(variants) >= 2:
            layout = {"name": "layout", "options": variants}
        child = None
        if is_container:
            cs = next((c["childShape"] for c in ms if c.get("childShape")), None)
            child_fields = fields_from_shape(cs) if cs else []
            child = {
                "name": title_case(ld["role"]) + " Item",
                "nodeType": f"{ns}:{camel(ld['role'])}Item",
                "fields": child_fields or [{"name": "title", "type": "string", "i18n": True, "mandatory": False}],
            }
            item_frag = next((c.get("itemHtmlFragment") for c in ms
                              if c.get("itemHtmlFragment")), None)
            if item_frag:
                child["htmlFragment"] = item_frag
        needs_mr = bool(d.get("mainResource"))
        components.append({
            "name": title_case(ld["role"]),
            "nodeType": node,
            "coversRoles": [c["role"] for c in ms],
            "isContainer": is_container,
            "childType": child,
            "needsMainResource": needs_mr,
            # downstream alias (v1 pipeline vocabulary): a mainResource entity is
            # rendered by a fullPage template
            "needsFullPage": needs_mr,
            # Islands hint: DOM carried forms/media/JS-widget markers
            "interactive": any(c.get("interactive") for c in ms),
            # P2: promoted instances render via skeleton views (pixel-exact +
            # editable fields) — same mechanism for both A/B arms
            "skeleton": True,
            # representative source markup per covered role (see html-fragments/)
            "htmlFragments": {c["role"]: c["htmlFragment"]
                              for c in ms if c.get("htmlFragment")},
            "layoutProperty": layout,
            "views": [{"name": v} for v in (d.get("views") or ["default"])],
            "fields": fields,
            "frequency": sum(c["frequency"] for c in ms),
        })

    # ── detail-page (mainResource) flagging — deterministic, from semantic_extract ──
    # A detected detail cluster names an entity role; the component that covers it
    # (or, failing that, the most of its facet roles) is a mainResource type and
    # gets a fullPage template. This is what unblocks pixel-perfect detail pages.
    detail_tpls = candidates.get("detailTemplates", []) or []
    entity_map = {dt["entityRole"]: dt for dt in detail_tpls}
    extra_templates = []
    for dt in detail_tpls:
        facets = set(dt.get("facetRoles", []))
        target, best = None, 0
        for comp in components:
            covers = set(comp["coversRoles"])
            if dt["entityRole"] in covers:            # direct hit on the entity role
                target, best = comp, 10_000
                break
            overlap = len(covers & facets)            # fallback: covers most facets
            if overlap > best:
                target, best = comp, overlap
        if not target or best < 1:
            continue
        target["needsMainResource"] = True
        target["needsFullPage"] = True
        target["detailOf"] = dt["detailOf"]

        # Enrich the entity with its own core fields: fold the scalar-content facet
        # shapes (title / body / image / link) into the entity, so the article node
        # carries title+body+image itself. Container facets (FAQ, related-content
        # lists) stay separate components placed in the detail template.
        by_role = defaultdict(list)
        for c in candidates["components"] + candidates.get("nestedParts", []):
            by_role[c["role"]].append(c)
        fold_shape = set()
        for role in target["coversRoles"] + list(facets):
            for c in by_role.get(role, []):
                if not c.get("isContainer"):
                    fold_shape |= set(c.get("dataShape", []))
        if fold_shape:
            merged = {f["name"]: f for f in target.get("fields", [])}
            for f in fields_from_shape(sorted(fold_shape)):
                merged.setdefault(f["name"], f)
            target["fields"] = list(merged.values())
        extra_templates.append({
            "name": camel(dt["detailOf"]) + "Detail",
            "kind": "detail",
            "pages": dt["pages"],
            "mainResourceType": target["nodeType"],
            "listingOf": dt["detailOf"],
            "listingPageExists": dt.get("listingPageExists", False),
            "confidence": dt.get("confidence"),
        })

    seen_names = {t.get("name") for t in templates if isinstance(t, dict)}
    templates = list(templates) + [t for t in extra_templates if t["name"] not in seen_names]

    # cross-cutting: deterministic from candidate set
    xcut = []
    for c in candidates.get("crossCutting", []):
        entry = {
            "name": title_case(c["role"]),
            "nodeType": f"{ns}:{camel(c['role'])}",
            "area": "nav" if "nav" in c["role"] else c["position"],
            "fields": fields_from_shape(c["dataShape"]),
            "coversRole": c["role"],
            "interactive": bool(c.get("interactive")),
        }
        if c.get("htmlFragment"):
            entry["htmlFragment"] = c["htmlFragment"]
        xcut.append(entry)

    # instance→type map: source role (as emitted per-instance by semantic_extract
    # and by extract_content's semantic adapter) → JCR nodeType. This is the
    # contract load_content.build_type_map() consumes for v2 manifests (the v1
    # equivalent was components[].sxaSource).
    instance_type_map = {}
    for comp in components:
        for role in comp["coversRoles"]:
            instance_type_map[role.lower()] = comp["nodeType"]
    for x in xcut:
        instance_type_map[x["coversRole"].lower()] = x["nodeType"]
    # always-nested roles load as the child type of their dominant parent's
    # container — extract_fields stops at nested component boundaries, so without
    # this mapping their text would never reach the JCR (loader skips unmapped)
    for c in candidates.get("nestedParts", []) or []:
        parents = c.get("commonParents") or {}
        dom_parent = max(parents.items(), key=lambda kv: kv[1])[0] if parents else None
        if not dom_parent:
            continue
        for comp in components:
            if dom_parent in comp["coversRoles"] and comp.get("childType"):
                instance_type_map.setdefault(c["role"].lower(),
                                             comp["childType"]["nodeType"])
                break

    # passthrough type (P1.2): uncovered main-region content loads verbatim as
    # ns:rawHtml — the guarantee that nothing is dropped (fidelity invariant §2)
    instance_type_map["rawhtml"] = f"{ns}:rawHtml"

    return {"crossCutting": xcut, "components": components, "templates": templates,
            "typeCount": len(components), "instanceTypeMap": instance_type_map,
            "passthroughType": f"{ns}:rawHtml"}


def partition_gate(candidates, groups):
    content_ids = set(c["candidateId"] for c in candidates["components"])
    used = [m for g in groups for m in g]
    used_set = set(used)
    unknown = [m for m in used if m not in content_ids]
    missing = sorted(content_ids - used_set)
    dupes = [m for m, k in Counter(used).items() if k > 1]
    return unknown, missing, dupes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--group")
    ap.add_argument("--consensus", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ns", default="ns", help="module namespace prefix (agnostic; e.g. usg)")
    args = ap.parse_args()

    cand = load(args.candidates)
    content_ids = set(c["candidateId"] for c in cand["components"])

    if args.consensus:
        files = []
        for pat in args.consensus:
            files += sorted(glob.glob(pat)) if any(ch in pat for ch in "*?[") else [pat]
        groups, decide = consensus_groups(content_ids, files)
        templates = []  # templates handled separately at consensus (kept from modal below)
        # pick templates from the run with the median template count
        tcs = []
        for gf in files:
            g = load(gf)
            tcs.append((len(g.get("templates", []) or []), g.get("templates", [])))
        tcs.sort(key=lambda x: x[0])
        templates = tcs[len(tcs) // 2][1] if tcs else []
    else:
        groups, decide, templates = single_groups(content_ids, args.group)

    unknown, missing, dupes = partition_gate(cand, groups)
    manifest = assemble(cand, groups, decide, templates, ns=args.ns)

    # Sanitize editor-hostile type names (leaked CSS-module hashes / framework
    # class fragments) to clean shape-derived names BEFORE the naming gate — the
    # grouping pass is a non-deterministic LLM, so this belt keeps every shipped
    # type editor-readable AND field-mapped (unmapped junk types crater the
    # contribution gate). Recorded in the manifest for the operator.
    renamed = sanitize_type_names(manifest, ns=args.ns)
    if renamed:
        manifest["sanitizedTypeNames"] = renamed

    violations = naming_violations(manifest)
    total_types = len(manifest["components"]) + len(manifest["crossCutting"])
    manifest["namingViolations"] = violations
    manifest["namingQuality"] = (
        "good" if not violations
        else "poor" if len(violations) > max(2, total_types // 3)
        else "mixed"
    )

    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[assemble] {args.out}: {len(manifest['components'])} components, "
          f"{len(manifest['crossCutting'])} cross-cutting, {len(templates)} templates")
    gate_ok = True
    if unknown:
        print(f"  [no-new-types] FAIL — hallucinated/unknown ids: {unknown}")
        gate_ok = False
    if missing:
        print(f"  [coverage] FAIL — candidates not assigned to any group: {missing}")
        gate_ok = False
    if dupes:
        print(f"  [partition] FAIL — ids in >1 group: {dupes}")
        gate_ok = False
    if gate_ok:
        print("  [partition gate] PASS — exact partition of content candidates")
    # Naming gate: a WARN, never a hard exit — the model is structurally usable, but
    # the operator must see that N type names are editor-hostile before templatization.
    if violations:
        print(f"  [naming gate] {manifest['namingQuality'].upper()} — "
              f"{len(violations)}/{total_types} editor-hostile type names:")
        for v in violations[:12]:
            print(f"      ✗ {v['nodeType']}: {v['reason']}")
    else:
        print("  [naming gate] GOOD — all type names are editor-readable")
    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
