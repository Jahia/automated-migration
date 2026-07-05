#!/usr/bin/env python3
"""gen_bundles.py — editor-UI field LABELS + ui.tooltips (EN/FR) for resource
bundles (P5.6; rule 18 + i18n.md).

These are strings of the EDITING INTERFACE (the Content-Editor chrome an author
sees), NOT content a site visitor reads — so EN/FR here is the ONE sanctioned
exception to "never generate content" (Julian, 2026-07-04). They are judged by
i18n-check (EN/FR key parity) and by G6 (every wired prop is a labelled rw field).

The problem this fixes: the current bundles are boilerplate — every richtext is
"Rich text content. Editors can format it...", every title "Main heading
displayed by this component.". Julian wants labels that are SHORT + editorial and
tooltips that are ONE genuinely-useful sentence tied to what the field is FOR in
THAT component (its skeleton context), not a template.

Input:  workflow-output/component-manifest.json (types + child types + fields),
        with each field's role inferred from name + a truncated skeleton/HTML
        excerpt for context. Cross-cutting (Header/Footer) included.
One DeepSeek json_object call per BATCH of components (not per field). The model
returns, per (type, field): a short EN + FR label and a one-sentence EN + FR
tooltip. Type-level labels come from the manifest name (already clean after
name_model) — the model only translates the FR type label.

Output (NO --apply):
  workflow-output/bundle-proposals.json    {en:{key:val}, fr:{key:val}} + per-type
--apply: writes/patches the module resource bundles IN PLACE (future runs only):
  settings/resources/<module>_en.properties  and  _fr.properties
  Existing files are re-emitted sorted-by-type with the ─── headers the repo uses;
  a .bak is kept. Keys NOT covered by the manifest (JCR Query / Grid Row / Raw
  HTML boilerplate + contrib slot mixins) are PRESERVED verbatim from the current
  file so --apply never drops a hand-maintained key.

Usage:
  python3 orchestration/lib/gen_bundles.py projects/<p> [--apply]
      [--module NAME] [--ns NS] [--batch-size N] [--dry-run-limit N]
      [--manifest PATH] [--out PATH] [--selftest]
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


SKELETON_EXCERPT_CHARS = 260


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
    return node_type.split(":", 1)[-1] if node_type else node_type


def _namespace(node_type: str) -> str:
    return node_type.split(":", 1)[0] if ":" in (node_type or "") else ""


def _skeleton_excerpt(project_path: str, comp: dict) -> str:
    """A dense, truncated peek at the component markup for tooltip context."""
    frags = comp.get("htmlFragments") or {}
    frag = comp.get("htmlFragment")
    rel = next(iter(frags.values())) if isinstance(frags, dict) and frags else frag
    if not rel:
        return ""
    path = os.path.join(_proj_root(project_path), "workflow-output", rel)
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
    except Exception:  # noqa: BLE001
        return ""
    txt = re.sub(r"<!--.*?-->", " ", txt, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)     # tags -> space; keep visible text
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:SKELETON_EXCERPT_CHARS]


def _iter_type_units(manifest: dict):
    """Yield (typeLocalName, humanLabel, fields[], skeletonExcerptKey, comp) for
    every type an editor sees: cross-cutting + components + child item types."""
    for cc in manifest.get("crossCutting", []) or []:
        yield (_local_name(cc.get("nodeType", "")), cc.get("name"),
               cc.get("fields", []), cc)
    for c in manifest.get("components", []) or []:
        yield (_local_name(c.get("nodeType", "")), c.get("name"),
               c.get("fields", []), c)
        child = c.get("childType")
        if child:
            yield (_local_name(child.get("nodeType", "")), child.get("name"),
                   child.get("fields", []), {**c, "_isChild": True})


_SYSTEM = (
    "You write CONTENT-EDITOR field labels and tooltips for a headless CMS. These "
    "are strings an EDITOR sees in the authoring interface — never text a visitor "
    "reads. For each field you get the component it belongs to and a short excerpt "
    "of that component's markup for context. Produce:\n"
    "- label: 2-3 words, Title Case, what the editor calls this field.\n"
    "- tooltip: ONE useful sentence describing what filling this field DOES in "
    "THIS component (its role/placement), NOT generic boilerplate. Bad: 'Rich "
    "text content. Editors can format it.' Good: 'Body copy shown beside the "
    "hero image on this banner.'\n"
    "- Provide both English (en) and a REAL French (fr) translation of label and "
    "tooltip (not a copy of the English).\n"
    "Special field names: 'title' = the heading; 'body'/'text' = rich body copy; "
    "'image' = a media pick from the library; 'j:linkType' = a call-to-action "
    "link (internal page / external URL / none); 'linkLabel' = the link's visible "
    "text. Reply with a single JSON object, no prose."
)


def _build_user_prompt(units: list[dict]) -> str:
    lines = ["FIELDS to label (grouped by component):", ""]
    payload = []
    for u in units:
        payload.append({
            "type": u["type"],
            "component": u["label"],
            "context": u["excerpt"],
            "fields": u["fields"],
        })
    lines.append(json.dumps(payload, ensure_ascii=False, indent=1))
    lines.append("")
    lines.append(
        'Return JSON: {"types":[{"type":"<type>","labelFr":"<FR component label>",'
        '"fields":[{"name":"<field>","labelEn":"..","labelFr":"..",'
        '"tooltipEn":"..","tooltipFr":".."}]}]}. Cover EVERY field of EVERY type.'
    )
    return "\n".join(lines)


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def propose_bundles(project_path: str, manifest: dict, *, batch_size: int,
                    dry_run_limit: int | None,
                    client: "llm_call.LLMClient | None" = None) -> dict:
    """Return {"types": {typeLocal: {labelEn, labelFr, fields:{name:{...}}}}, "batches": n}."""
    units = []
    for tlocal, tlabel, fields, comp in _iter_type_units(manifest):
        if not tlocal:
            continue
        field_names = [f.get("name") for f in fields if f.get("name")]
        if not field_names:
            # a type with no editable fields still gets a type label (from manifest)
            units.append({"type": tlocal, "label": tlabel, "fields": [], "excerpt": ""})
            continue
        units.append({"type": tlocal, "label": tlabel, "fields": field_names,
                       "excerpt": _skeleton_excerpt(project_path, comp)})
    if dry_run_limit:
        units = units[:dry_run_limit]

    if client is None:
        client = llm_call.LLMClient(project_path=project_path, caller="gen_bundles.py")

    types: dict[str, dict] = {}
    # pre-seed type labels from the manifest (already clean); FR filled by model
    label_en_by_type = {u["type"]: u["label"] for u in units}

    to_ask = [u for u in units if u["fields"]]
    n_batches = 0
    for batch in _chunks(to_ask, batch_size):
        n_batches += 1
        data = client.chat_json(
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": _build_user_prompt(batch)}],
            temperature=0.0,
            caller=f"gen_bundles.py:batch{n_batches}",
            meta={"batch": n_batches, "types": len(batch)},
        )
        for t in data.get("types", []) or []:
            tl = t.get("type")
            if not tl:
                continue
            entry = types.setdefault(tl, {"labelEn": label_en_by_type.get(tl, tl),
                                          "labelFr": None, "fields": {}})
            if t.get("labelFr"):
                entry["labelFr"] = t["labelFr"].strip()
            for f in t.get("fields", []) or []:
                fn = f.get("name")
                if not fn:
                    continue
                entry["fields"][fn] = {
                    "labelEn": (f.get("labelEn") or "").strip(),
                    "labelFr": (f.get("labelFr") or "").strip(),
                    "tooltipEn": (f.get("tooltipEn") or "").strip(),
                    "tooltipFr": (f.get("tooltipFr") or "").strip(),
                }
    # ensure every unit's type label is present even if it had no fields
    for u in units:
        types.setdefault(u["type"], {"labelEn": u["label"], "labelFr": None, "fields": {}})
    return {"types": types, "batches": n_batches}


# ── properties emission ──────────────────────────────────────────────
def _key_ns(ns: str, tlocal: str) -> str:
    """asr + heroBanner -> asr_heroBanner (rule: ':' -> '_'; mix ns 'asrmix')."""
    return f"{ns}_{tlocal}"


def _parse_properties(path: str) -> "list[tuple[str,str]]":
    """Read a .properties file into ordered (key, value) pairs (comments dropped;
    we re-emit our own headers). Non-key lines are skipped."""
    pairs = []
    if not os.path.isfile(path):
        return pairs
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = line.partition("=")
            pairs.append((k.strip(), v))
    return pairs


def build_properties(manifest: dict, result: dict, ns: str, mixns: str,
                     existing_en: str | None, existing_fr: str | None) -> tuple[str, str]:
    """Return (en_text, fr_text). Manifest types get generated keys; keys present
    in the existing file that we DON'T generate (JCR Query, Grid Row, Raw HTML,
    contrib slot mixins) are preserved verbatim at the end."""
    types = result["types"]

    # local -> (ns, humanLabelEn, labelFr, fields{name:{...}}) in manifest order
    ordered = []
    seen = set()
    for tlocal, tlabel, fields, comp in _iter_type_units(manifest):
        if not tlocal or tlocal in seen:
            continue
        seen.add(tlocal)
        info = types.get(tlocal, {"labelEn": tlabel, "labelFr": None, "fields": {}})
        ordered.append((tlocal, tlabel, info, fields))

    generated_keys = set()

    def emit(lang: str) -> list[str]:
        out = []
        for tlocal, tlabel, info, fields in ordered:
            key = _key_ns(ns, tlocal)
            type_label = (info.get("labelFr") if lang == "fr" and info.get("labelFr")
                          else info.get("labelEn") or tlabel)
            out.append(f"# ─── {tlabel} ───")
            out.append(f"{key}={type_label}")
            generated_keys.add(key)
            for f in fields:
                fn = f.get("name")
                if not fn:
                    continue
                fmeta = info["fields"].get(fn, {})
                lab = fmeta.get("labelFr" if lang == "fr" else "labelEn") or fn.capitalize()
                tip = fmeta.get("tooltipFr" if lang == "fr" else "tooltipEn") or ""
                fkey = f"{key}.{fn}"
                out.append(f"{fkey}={lab}")
                generated_keys.add(fkey)
                if tip:
                    out.append(f"{fkey}.ui.tooltip={tip}")
                    generated_keys.add(f"{fkey}.ui.tooltip")
            out.append("")
        return out

    en_lines = emit("en")
    fr_lines = emit("fr")

    # preserve non-manifest keys (contrib mixins, JCR Query, Grid Row, Raw HTML)
    def preserve(existing_path_text: "list[tuple[str,str]]", lines: list[str]):
        extra = [(k, v) for (k, v) in existing_path_text if k not in generated_keys]
        if not extra:
            return
        lines.append("# ─── preserved (JCR Query / Grid Row / passthrough / contrib slots) ───")
        for k, v in extra:
            lines.append(f"{k}={v}")
        lines.append("")

    en_existing = _parse_properties_text(existing_en)
    fr_existing = _parse_properties_text(existing_fr)
    preserve(en_existing, en_lines)
    preserve(fr_existing, fr_lines)

    return "\n".join(en_lines).rstrip() + "\n", "\n".join(fr_lines).rstrip() + "\n"


def _parse_properties_text(text: str | None) -> "list[tuple[str,str]]":
    pairs = []
    if not text:
        return pairs
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = raw.partition("=")
        pairs.append((k.strip(), v))
    return pairs


# ── selftest ────────────────────────────────────────────────────────
def _selftest() -> int:
    manifest = {
        "crossCutting": [],
        "components": [
            {"name": "Hero Banner", "nodeType": "tst:heroBanner",
             "fields": [{"name": "title"}, {"name": "image"}, {"name": "j:linkType"}]},
        ],
    }

    class _Fake:
        def chat_json(self, messages, **kw):
            return {"types": [{"type": "heroBanner", "labelFr": "Bannière Héros", "fields": [
                {"name": "title", "labelEn": "Heading", "labelFr": "Titre",
                 "tooltipEn": "The big heading on the banner.", "tooltipFr": "Le grand titre de la bannière."},
                {"name": "image", "labelEn": "Background", "labelFr": "Image de fond",
                 "tooltipEn": "The banner background image.", "tooltipFr": "L'image de fond de la bannière."},
                {"name": "j:linkType", "labelEn": "CTA Link", "labelFr": "Lien CTA",
                 "tooltipEn": "Where the banner button points.", "tooltipFr": "La cible du bouton de la bannière."},
            ]}]}

    res = propose_bundles("projects/tst", manifest, batch_size=50, dry_run_limit=None, client=_Fake())
    assert "heroBanner" in res["types"], res
    en, fr = build_properties(manifest, res, "tst", "tstmix", None, None)
    assert "tst_heroBanner=Hero Banner" in en, en
    assert "tst_heroBanner.title=Heading" in en, en
    assert "tst_heroBanner.title.ui.tooltip=The big heading on the banner." in en, en
    assert "tst_heroBanner=Bannière Héros" in fr, fr
    assert "tst_heroBanner.image.ui.tooltip=L'image de fond de la bannière." in fr, fr
    # EN/FR key parity (i18n-check requirement)
    en_keys = {k for k, _ in _parse_properties_text(en)}
    fr_keys = {k for k, _ in _parse_properties_text(fr)}
    assert en_keys == fr_keys, (en_keys ^ fr_keys)
    print("gen_bundles selftest OK")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?")
    ap.add_argument("--apply", action="store_true", help="patch the module bundles (future runs only)")
    ap.add_argument("--module", default=None, help="module name (default = project basename)")
    ap.add_argument("--ns", default=None, help="namespace prefix (default inferred from manifest)")
    ap.add_argument("--mixns", default=None)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--dry-run-limit", type=int, default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()
    if not a.project:
        ap.error("project is required (unless --selftest)")

    manifest = _read_json(_manifest_path(a.project, a.manifest))
    ns = a.ns
    if not ns:
        for c in manifest.get("components", []):
            ns = _namespace(c.get("nodeType", ""))
            if ns:
                break
    mixns = a.mixns or (f"{ns}mix" if ns else "mix")

    result = propose_bundles(a.project, manifest, batch_size=a.batch_size,
                             dry_run_limit=a.dry_run_limit)

    wo = os.path.join(_proj_root(a.project), "workflow-output")
    out = a.out or os.path.join(wo, "bundle-proposals.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"project": a.project, "namespace": ns,
                   "generatedBy": "gen_bundles.py (editor-UI chrome; EN/FR; never site content)",
                   **result}, f, indent=2, ensure_ascii=False)
    n_fields = sum(len(t["fields"]) for t in result["types"].values())
    print(f"[gen_bundles] proposals -> {out} ({len(result['types'])} types, "
          f"{n_fields} fields, {result['batches']} LLM batch(es))")

    if a.apply:
        module = a.module or os.path.basename(_proj_root(a.project))
        res_dir = os.path.join(_proj_root(a.project), "settings", "resources")
        en_path = os.path.join(res_dir, f"{module}_en.properties")
        fr_path = os.path.join(res_dir, f"{module}_fr.properties")
        existing_en = open(en_path, encoding="utf-8").read() if os.path.isfile(en_path) else None
        existing_fr = open(fr_path, encoding="utf-8").read() if os.path.isfile(fr_path) else None
        en_text, fr_text = build_properties(manifest, result, ns or "ns", mixns,
                                            existing_en, existing_fr)
        os.makedirs(res_dir, exist_ok=True)
        for path, text, old in ((en_path, en_text, existing_en), (fr_path, fr_text, existing_fr)):
            if old is not None and not os.path.exists(path + ".bak"):
                with open(path + ".bak", "w", encoding="utf-8") as f:
                    f.write(old)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        print(f"[gen_bundles] --apply: wrote {en_path} + {fr_path} (backups kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
