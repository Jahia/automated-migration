#!/usr/bin/env python3
"""name_model.py — generic, CMS-reusable NAMING of zones and components (P5.6).

Julian's directive (2026-07-04): component + zone names must be GENERIC and
REUSABLE by CMS contributors — not site-specific jargon (unless the component is
genuinely bespoke), no hash suffixes, PascalCase type name + a clean editorial
label. This mirrors migration rule 21 ("judge the component model editorially"),
moved from a manual review-gate note into a deterministic, LLM-assisted step.

This is METADATA generation, NOT content generation: DeepSeek proposes NAMES for
the MODEL (type names + editor labels), never any text a visitor reads. The names
are judged downstream by the model-review gate and by i18n-check / G6.

Input:  projects/<p>/workflow-output/component-manifest.json  (types + fields +
        coversRoles + frequency), plus the segmentation zone names from
        workflow-output/segment/*.segmentation.json (components[].name/kind) as
        extra CONTEXT for what each zone is on the page.
        Truncated html-fragment excerpts (workflow-output/html-fragments/*.html)
        give the model a peek at the real markup — TRUNCATED hard (never the full
        blob; this is naming, not extraction).

One DeepSeek call per reasonable BATCH (all components in a single json_object
call for a normal-sized manifest; auto-split if the manifest is very large), so
volume stays cheap. The model returns, per component:
  proposed PascalCase-ish label + camelCase nodeType local-name + rationale, and
  a merge group id for near-duplicate signatures (e.g. "Brands Logo Section" /
  "Brand Logos Section" -> one "Brand Logos" type).

Output (NO --apply):
  workflow-output/naming-proposals.json   machine-readable proposals + merges
  workflow-output/naming-proposals.md      human review: current -> proposed +
                                            rationale + merge candidates
With --apply: rewrites component-manifest.json IN PLACE (renames + merges applied)
  BEFORE CND emission — for FUTURE runs only, NEVER a deployed module. A .bak of
  the manifest is written next to it. instanceTypeMap is rewired so no coversRole
  is orphaned; merged types fold their coversRoles/pages/fields together.

Usage:
  python3 orchestration/lib/name_model.py projects/<p> [--apply]
      [--model NAME] [--batch-size N] [--out-json PATH] [--out-md PATH]
      [--manifest PATH] [--dry-run-limit N]   # dry-run-limit: name only the first
                                              # N components (cheap validation)
      [--selftest]                            # offline fixture, no network
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    from . import llm_call  # type: ignore
except Exception:  # noqa: BLE001
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import llm_call  # type: ignore


HTML_EXCERPT_CHARS = 320   # truncated hard — naming needs a peek, not the blob
MAX_ROLES = 8


# ── helpers ───────────────────────────────────────────────────────────
def _proj_root(project_path: str) -> str:
    p = str(project_path).strip().rstrip("/")
    if "/" not in p and os.sep not in p:
        p = os.path.join("projects", p)
    return p


def _manifest_path(project_path: str, override: str | None) -> str:
    if override:
        return override
    return os.path.join(_proj_root(project_path), "workflow-output", "component-manifest.json")


def _read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _local_name(node_type: str) -> str:
    """asr:heroBanner -> heroBanner."""
    return node_type.split(":", 1)[-1] if node_type else node_type


def _namespace(node_type: str) -> str:
    return node_type.split(":", 1)[0] if ":" in (node_type or "") else ""


def _camel(local: str) -> str:
    """Normalise an arbitrary local-name candidate to camelCase (no spaces/hyphens)."""
    parts = re.split(r"[^A-Za-z0-9]+", local.strip())
    parts = [p for p in parts if p]
    if not parts:
        return local
    head = parts[0]
    head = head[0].lower() + head[1:] if head else head
    tail = "".join(w[:1].upper() + w[1:] for w in parts[1:])
    return head + tail


def _signature(comp: dict) -> str:
    """A stable structural signature for near-dup detection: sorted field names +
    isContainer + childType field names."""
    fields = sorted(f.get("name", "") for f in comp.get("fields", []))
    child = comp.get("childType") or {}
    child_fields = sorted(f.get("name", "") for f in child.get("fields", []))
    return json.dumps({"c": bool(comp.get("isContainer")),
                       "f": fields, "cf": child_fields}, sort_keys=True)


def _zone_names(project_path: str) -> list[str]:
    """Distinct segmentation zone names across pages (context for the model)."""
    seg_dir = os.path.join(_proj_root(project_path), "workflow-output", "segment")
    names: list[str] = []
    seen = set()
    if not os.path.isdir(seg_dir):
        return names
    for fn in sorted(os.listdir(seg_dir)):
        if not fn.endswith(".segmentation.json"):
            continue
        try:
            d = _read_json(os.path.join(seg_dir, fn))
        except Exception:  # noqa: BLE001
            continue
        for c in d.get("components", []) or []:
            nm = c.get("name")
            kind = c.get("kind")
            if nm and (nm, kind) not in seen:
                seen.add((nm, kind))
                names.append(f"{nm} [{kind}]")
    return names


def _html_excerpt(project_path: str, comp: dict) -> str:
    frags = comp.get("htmlFragments") or {}
    frag = comp.get("htmlFragment")
    rel = None
    if isinstance(frags, dict) and frags:
        rel = next(iter(frags.values()))
    elif frag:
        rel = frag
    if not rel:
        return ""
    path = os.path.join(_proj_root(project_path), "workflow-output", rel)
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
    except Exception:  # noqa: BLE001
        return ""
    # strip HTML comments + collapse whitespace so the excerpt is dense
    txt = re.sub(r"<!--.*?-->", " ", txt, flags=re.S)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:HTML_EXCERPT_CHARS]


# ── LLM prompt ──────────────────────────────────────────────────────────
_SYSTEM = (
    "You name components for a headless CMS being populated by MIGRATING a website. "
    "You produce ONLY metadata (type names + editor labels) — never any content a "
    "visitor reads. Names must be GENERIC and REUSABLE by content editors on future "
    "pages, following these hard rules:\n"
    "1. NO hash/random suffixes (e.g. never 'callToActionCard9pqm4').\n"
    "2. NO site-specific jargon UNLESS the component is genuinely bespoke to this "
    "site's domain; prefer the generic CMS term (a 'brands-logo-section' is a "
    "'Logo Wall'/'Logo Strip'; an 'asr-carousel' is a 'Carousel'; a "
    "'wrap-container' is a generic 'Content Section').\n"
    "3. label = Title Case, human, editorial (2-4 words). nodeType = camelCase "
    "local name, no namespace prefix, no spaces.\n"
    "4. When two or more components have the SAME structural signature and clearly "
    "describe the same block (e.g. 'Brands Logo Section' and 'Brand Logos "
    "Section'), MERGE them: give them a shared mergeGroup id and ONE merged label "
    "+ nodeType. Pick the most generic/reusable of the merged names.\n"
    "5. A component that is truly one-off content (not reusable) keeps a specific "
    "but still clean name. Never invent a fancier name than the block warrants.\n"
    "Reply with a single JSON object, no prose."
)


def _build_user_prompt(components: list[dict], zone_names: list[str]) -> str:
    lines = []
    lines.append("ZONE NAMES observed by vision segmentation (context only):")
    lines.append(", ".join(zone_names[:60]) if zone_names else "(none)")
    lines.append("")
    lines.append("COMPONENTS to name (current name is a starting point, feel free to change it):")
    payload = []
    for c in components:
        payload.append({
            "id": _local_name(c.get("nodeType", "")) or c.get("name"),
            "currentName": c.get("name"),
            "currentNodeType": _local_name(c.get("nodeType", "")),
            "isContainer": bool(c.get("isContainer")),
            "hasChildItems": bool(c.get("childType")),
            "coversRoles": (c.get("coversRoles") or [])[:MAX_ROLES],
            "fields": [f.get("name") for f in c.get("fields", [])],
            "frequency": c.get("frequency"),
            "signature": _signature(c),
            "htmlExcerpt": c.get("_htmlExcerpt", ""),
        })
    lines.append(json.dumps(payload, ensure_ascii=False, indent=1))
    lines.append("")
    lines.append(
        'Return JSON: {"proposals":[{"id":"<the id above>","label":"Title Case",'
        '"nodeType":"camelCase","rationale":"one short sentence",'
        '"mergeGroup":"<shared id or null>"}]}. Include EVERY id exactly once.'
    )
    return "\n".join(lines)


# ── core ────────────────────────────────────────────────────────────────
def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def propose_names(project_path: str, manifest: dict, *, model: str | None,
                  batch_size: int, dry_run_limit: int | None,
                  client: "llm_call.LLMClient | None" = None) -> dict:
    """Return {"proposals": {id: {...}}, "batches": n, "merges": {group:[ids]}}.

    One json_object call per batch. `client` may be injected (selftest)."""
    components = list(manifest.get("components", []))
    if dry_run_limit:
        components = components[:dry_run_limit]
    # attach truncated html excerpts
    for c in components:
        c["_htmlExcerpt"] = _html_excerpt(project_path, c)

    if client is None:
        client = llm_call.LLMClient(project_path=project_path, caller="name_model.py")

    proposals: dict[str, dict] = {}
    n_batches = 0
    for batch in _chunks(components, batch_size):
        n_batches += 1
        zone_names = _zone_names(project_path)
        user = _build_user_prompt(batch, zone_names)
        data = client.chat_json(
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": user}],
            temperature=0.0,
            caller=f"name_model.py:batch{n_batches}",
            meta={"batch": n_batches, "components": len(batch)},
        )
        for pr in data.get("proposals", []) or []:
            cid = pr.get("id")
            if not cid:
                continue
            proposals[str(cid)] = {
                "label": (pr.get("label") or "").strip(),
                "nodeType": _camel((pr.get("nodeType") or "").strip()),
                "rationale": (pr.get("rationale") or "").strip(),
                "mergeGroup": pr.get("mergeGroup") or None,
            }

    # strip the transient excerpts back off the manifest components
    for c in components:
        c.pop("_htmlExcerpt", None)

    # group merges
    merges: dict[str, list[str]] = {}
    for cid, pr in proposals.items():
        g = pr.get("mergeGroup")
        if g:
            merges.setdefault(str(g), []).append(cid)
    merges = {g: ids for g, ids in merges.items() if len(ids) >= 2}
    return {"proposals": proposals, "batches": n_batches, "merges": merges}


def build_report(project_path: str, manifest: dict, result: dict) -> tuple[dict, str]:
    """(json_obj, markdown) for the proposals."""
    ns = ""
    for c in manifest.get("components", []):
        ns = _namespace(c.get("nodeType", "")) or ns
        if ns:
            break
    proposals = result["proposals"]
    comps_by_id = {(_local_name(c.get("nodeType", "")) or c.get("name")): c
                   for c in manifest.get("components", [])}

    json_rows = []
    for cid, c in comps_by_id.items():
        pr = proposals.get(cid, {})
        cur_type = _local_name(c.get("nodeType", ""))
        cur_name = c.get("name")
        new_type = pr.get("nodeType") or cur_type
        new_name = pr.get("label") or cur_name
        changed = (new_type != cur_type) or (new_name != cur_name)
        json_rows.append({
            "id": cid,
            "currentName": cur_name,
            "currentNodeType": f"{ns}:{cur_type}" if ns else cur_type,
            "proposedName": new_name,
            "proposedNodeType": f"{ns}:{new_type}" if ns else new_type,
            "changed": changed,
            "mergeGroup": pr.get("mergeGroup"),
            "rationale": pr.get("rationale", ""),
            "signature": _signature(c),
        })

    json_obj = {
        "project": project_path,
        "namespace": ns,
        "generatedBy": "name_model.py (deepseek-direct metadata; never site content)",
        "batches": result["batches"],
        "proposals": json_rows,
        "merges": result["merges"],
    }

    # markdown
    md = []
    md.append(f"# Naming proposals — {os.path.basename(_proj_root(project_path))}")
    md.append("")
    md.append("Generic, CMS-reusable names for zones/components (P5.6, metadata only — "
              "never site content). Review, then `--apply` to rewrite the manifest "
              "BEFORE CND emission (future runs only).")
    md.append("")
    changed_rows = [r for r in json_rows if r["changed"]]
    md.append(f"**{len(changed_rows)}/{len(json_rows)} components proposed for renaming.**")
    md.append("")
    md.append("| Current | Proposed | Rationale |")
    md.append("|---|---|---|")
    for r in json_rows:
        arrow = "→" if r["changed"] else "="
        md.append(f"| `{r['currentNodeType']}` — {r['currentName']} | {arrow} "
                  f"`{r['proposedNodeType']}` — {r['proposedName']} | {r['rationale']} |")
    md.append("")
    if result["merges"]:
        md.append("## Merge candidates (near-duplicate signatures)")
        md.append("")
        for g, ids in result["merges"].items():
            names = [comps_by_id[i].get("name", i) for i in ids if i in comps_by_id]
            target = proposals.get(ids[0], {}).get("label") or names[0] if names else g
            md.append(f"- **{target}** ⟵ merge of: " + ", ".join(f"`{n}`" for n in names))
        md.append("")
    else:
        md.append("_No merge candidates found._")
        md.append("")
    return json_obj, "\n".join(md)


def apply_to_manifest(manifest: dict, result: dict) -> dict:
    """Rewrite type names + fold merges INTO the manifest (returns a new dict).

    Renames every component's name/nodeType per proposal; for each merge group,
    the FIRST id is the survivor and later ids fold their coversRoles/pages/fields
    into it (union) and are dropped. instanceTypeMap is rewired so no coversRole
    is orphaned. Also updates crossCutting names/labels if proposed (rare)."""
    import copy
    m = copy.deepcopy(manifest)
    proposals = result["proposals"]
    comps = m.get("components", [])

    def cid_of(c):
        return _local_name(c.get("nodeType", "")) or c.get("name")

    ns = ""
    for c in comps:
        ns = _namespace(c.get("nodeType", "")) or ns
        if ns:
            break

    # 1. resolve merge groups: survivor id -> list of folded ids
    survivors: dict[str, list[str]] = {}
    folded_into: dict[str, str] = {}
    for g, ids in result["merges"].items():
        keep = ids[0]
        survivors[keep] = ids[1:]
        for other in ids[1:]:
            folded_into[other] = keep

    by_id = {cid_of(c): c for c in comps}

    # 2. fold merged components into survivors (union coversRoles/pages/fields)
    for keep, others in survivors.items():
        base = by_id.get(keep)
        if not base:
            continue
        for oid in others:
            oc = by_id.get(oid)
            if not oc:
                continue
            roles = set(base.get("coversRoles") or []) | set(oc.get("coversRoles") or [])
            base["coversRoles"] = sorted(roles)
            pages = list(dict.fromkeys((base.get("pages") or []) + (oc.get("pages") or [])))
            base["pages"] = pages
            base["frequency"] = (base.get("frequency") or 0) + (oc.get("frequency") or 0)
            # union fields by name (keep base's field defs, add missing)
            have = {f.get("name") for f in base.get("fields", [])}
            for f in oc.get("fields", []) or []:
                if f.get("name") not in have:
                    base.setdefault("fields", []).append(f)
                    have.add(f.get("name"))

    # 3. drop folded components
    new_comps = [c for c in comps if cid_of(c) not in folded_into]

    # 4. rename survivors + all remaining components
    rename_type: dict[str, str] = {}   # old nodeType -> new nodeType
    for c in new_comps:
        cid = cid_of(c)
        pr = proposals.get(cid) or {}
        new_local = pr.get("nodeType") or _local_name(c.get("nodeType", ""))
        new_label = pr.get("label") or c.get("name")
        old_type = c.get("nodeType")
        new_type = f"{ns}:{new_local}" if ns else new_local
        if old_type and old_type != new_type:
            rename_type[old_type] = new_type
        c["name"] = new_label
        c["nodeType"] = new_type
        # child type: derive from the new local name
        child = c.get("childType")
        if child and child.get("nodeType"):
            child_local = f"{new_local}Item"
            child_new = f"{ns}:{child_local}" if ns else child_local
            old_child = child.get("nodeType")
            if old_child != child_new:
                rename_type[old_child] = child_new
            child["nodeType"] = child_new
            child["name"] = f"{new_label} Item"
    m["components"] = new_comps

    # 5. rewire instanceTypeMap: role -> (renamed / folded) nodeType
    itm = m.get("instanceTypeMap") or {}
    folded_type: dict[str, str] = {}
    for oid, keep in folded_into.items():
        oc_type = None
        for c in comps:
            if cid_of(c) == oid:
                oc_type = c.get("nodeType")
                break
        keep_c = by_id.get(keep)
        if oc_type and keep_c:
            folded_type[oc_type] = keep_c.get("nodeType")
    new_itm = {}
    for role, t in itm.items():
        t2 = folded_type.get(t, t)      # fold first
        t2 = rename_type.get(t2, t2)    # then rename
        new_itm[role] = t2
    m["instanceTypeMap"] = new_itm

    m["typeCount"] = len(new_comps) + len(m.get("crossCutting", [])) + sum(
        1 for c in new_comps if c.get("childType"))
    m["namingApplied"] = True
    return m


# ── selftest fixture ────────────────────────────────────────────────────
def _selftest() -> int:
    manifest = {
        "components": [
            {"name": "Brands Logo Section", "nodeType": "tst:brandsLogoSection",
             "isContainer": False, "coversRoles": ["brands-logo"], "pages": ["a"],
             "frequency": 3, "fields": [{"name": "title"}, {"name": "image"}]},
            {"name": "Brand Logos Section", "nodeType": "tst:brandLogosSection",
             "isContainer": False, "coversRoles": ["brand-logos"], "pages": ["b"],
             "frequency": 2, "fields": [{"name": "title"}, {"name": "image"}]},
            {"name": "Wrap Container", "nodeType": "tst:wrapContainer9x",
             "isContainer": False, "coversRoles": ["wrap-container"], "pages": ["c"],
             "frequency": 1, "fields": [{"name": "text"}]},
        ],
        "crossCutting": [],
        "instanceTypeMap": {"brands-logo": "tst:brandsLogoSection",
                            "brand-logos": "tst:brandLogosSection",
                            "wrap-container": "tst:wrapContainer9x"},
        "typeCount": 3,
    }

    class _Fake:
        def chat_json(self, messages, **kw):
            return {"proposals": [
                {"id": "brandsLogoSection", "label": "Logo Wall", "nodeType": "logoWall",
                 "rationale": "generic logo strip", "mergeGroup": "logos"},
                {"id": "brandLogosSection", "label": "Logo Wall", "nodeType": "logoWall",
                 "rationale": "same as brandsLogoSection", "mergeGroup": "logos"},
                {"id": "wrapContainer9x", "label": "Content Section", "nodeType": "contentSection",
                 "rationale": "drop hash suffix + generic name", "mergeGroup": None},
            ]}

    res = propose_names("projects/tst", manifest, model=None, batch_size=50,
                        dry_run_limit=None, client=_Fake())
    assert "logos" in res["merges"], res["merges"]
    assert set(res["merges"]["logos"]) == {"brandsLogoSection", "brandLogosSection"}
    applied = apply_to_manifest(manifest, res)
    names = {c["nodeType"] for c in applied["components"]}
    assert "tst:logoWall" in names, names
    assert "tst:contentSection" in names, names
    assert len(applied["components"]) == 2, "merge should drop one component"
    # instanceTypeMap must not orphan a role and must point at the survivor
    itm = applied["instanceTypeMap"]
    assert itm["brands-logo"] == "tst:logoWall", itm
    assert itm["brand-logos"] == "tst:logoWall", itm
    assert itm["wrap-container"] == "tst:contentSection", itm
    # hash suffix gone
    assert not any("9x" in t for t in names), names
    print("name_model selftest OK")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?", help="projects/<name>")
    ap.add_argument("--apply", action="store_true", help="rewrite the manifest in place (future runs only)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--dry-run-limit", type=int, default=None,
                    help="name only the first N components (cheap validation)")
    ap.add_argument("--manifest", default=None, help="override manifest path")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()
    if not a.project:
        ap.error("project is required (unless --selftest)")

    mpath = _manifest_path(a.project, a.manifest)
    manifest = _read_json(mpath)
    result = propose_names(a.project, manifest, model=a.model,
                           batch_size=a.batch_size, dry_run_limit=a.dry_run_limit)
    json_obj, md = build_report(a.project, manifest, result)

    wo = os.path.join(_proj_root(a.project), "workflow-output")
    out_json = a.out_json or os.path.join(wo, "naming-proposals.json")
    out_md = a.out_md or os.path.join(wo, "naming-proposals.md")
    os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, indent=2, ensure_ascii=False)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[name_model] proposals -> {out_json}")
    print(f"[name_model] review    -> {out_md}")
    n_changed = sum(1 for r in json_obj["proposals"] if r["changed"])
    print(f"[name_model] {n_changed}/{len(json_obj['proposals'])} renamed, "
          f"{len(result['merges'])} merge group(s), {result['batches']} LLM batch(es)")

    if a.apply:
        bak = mpath + ".bak"
        if not os.path.exists(bak):
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
        applied = apply_to_manifest(manifest, result)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(applied, f, indent=2, ensure_ascii=False)
        print(f"[name_model] --apply: manifest rewritten ({mpath}); backup at {bak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
